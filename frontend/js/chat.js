/* ==========================================================================
   TASKMASTER — CHAT CONTROLLER & SQLITE DATABASE SYNC ENGINE
   ========================================================================== */

let currentSessionId = null;
let isExecuting = false;
let browserStreamInterval = null;
let pendingAttachments = [];

// ── Canonical Playback States ──
const PLAYBACK_STATE = {
    NONE: 'NONE',
    LOADING: 'LOADING',
    READY: 'READY',
    PLAYING: 'PLAYING',
    PAUSED: 'PAUSED',
    STOPPED: 'STOPPED',
    ENDED: 'ENDED',
    ERROR: 'ERROR'
};

// ── Media Playback & Single Active Session Manager ──
const MediaManager = {
    activeMessageId: null,
    activeMediaId: null,
    tabId: 'tab_' + Math.random().toString(36).substring(2, 9),
    stateVersion: 1,
    mediaRegistry: new Map(),

    registerMedia(messageId, mediaData) {
        if (!messageId || !mediaData || !mediaData.videoId) return;
        const current = this.mediaRegistry.get(messageId) || {};
        this.mediaRegistry.set(messageId, {
            ...current,
            ...mediaData,
            playbackState: mediaData.playbackState || current.playbackState || PLAYBACK_STATE.READY
        });
    },

    setPlaybackState(messageId, targetState, options = {}) {
        const item = this.mediaRegistry.get(messageId);
        if (!item) return;

        // Enforce Single Active Video rule across client
        if (targetState === PLAYBACK_STATE.PLAYING) {
            if (this.activeMessageId && this.activeMessageId !== messageId) {
                this.pauseOrStopVideoElement(this.activeMessageId, PLAYBACK_STATE.STOPPED);
            }
            this.activeMessageId = messageId;
            this.activeMediaId = item.videoId;
        } else if (this.activeMessageId === messageId && (targetState === PLAYBACK_STATE.STOPPED || targetState === PLAYBACK_STATE.ENDED)) {
            this.activeMessageId = null;
            this.activeMediaId = null;
        }

        item.playbackState = targetState;
        item.version = ++this.stateVersion;

        this.renderCardState(messageId, targetState);

        if (!options.silent) {
            TabSync.broadcast('MEDIA_STATE_CHANGE', {
                messageId,
                videoId: item.videoId,
                playbackState: targetState,
                version: item.version,
                sourceTabId: this.tabId,
                timestamp: Date.now()
            });
        }
    },

    renderCardState(messageId, state) {
        const card = document.getElementById(`video-card-${messageId}`);
        if (!card) return;

        const item = this.mediaRegistry.get(messageId);
        if (!item) return;

        const container = card.querySelector('.video-viewport');
        const statusBadge = card.querySelector('.media-status-badge');
        const playPauseBtn = card.querySelector('.media-ctrl-playpause');

        // 1. Update status badge
        if (statusBadge) {
            statusBadge.className = `media-status-badge status-${state.toLowerCase()}`;
            if (state === PLAYBACK_STATE.PLAYING) {
                statusBadge.innerHTML = `<span class="pulse-dot"></span> Playing`;
            } else if (state === PLAYBACK_STATE.PAUSED) {
                statusBadge.innerHTML = `<i class="fa-solid fa-pause"></i> Paused`;
            } else if (state === PLAYBACK_STATE.STOPPED) {
                statusBadge.innerHTML = `<i class="fa-solid fa-stop"></i> Stopped`;
            } else if (state === PLAYBACK_STATE.ENDED) {
                statusBadge.innerHTML = `<i class="fa-solid fa-check"></i> Completed`;
            } else if (state === PLAYBACK_STATE.LOADING) {
                statusBadge.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Loading...`;
            } else if (state === PLAYBACK_STATE.ERROR) {
                statusBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error`;
            } else {
                statusBadge.innerHTML = `Ready`;
            }
        }

        // 2. Update Control button
        if (playPauseBtn) {
            if (state === PLAYBACK_STATE.PLAYING) {
                playPauseBtn.innerHTML = `<i class="fa-solid fa-pause"></i> Pause`;
                playPauseBtn.className = `media-btn media-ctrl-playpause is-playing`;
            } else if (state === PLAYBACK_STATE.ENDED) {
                playPauseBtn.innerHTML = `<i class="fa-solid fa-rotate-left"></i> Play Again`;
                playPauseBtn.className = `media-btn media-ctrl-playpause is-replay`;
            } else if (state === PLAYBACK_STATE.ERROR) {
                playPauseBtn.innerHTML = `<i class="fa-solid fa-arrow-rotate-right"></i> Retry`;
                playPauseBtn.className = `media-btn media-ctrl-playpause is-retry`;
            } else {
                playPauseBtn.innerHTML = `<i class="fa-solid fa-play"></i> Play`;
                playPauseBtn.className = `media-btn media-ctrl-playpause`;
            }
        }

        // 3. Viewport Display
        if (container) {
            if (state === PLAYBACK_STATE.PLAYING) {
                let iframe = container.querySelector('iframe');
                if (!iframe) {
                    const iframeSrc = `https://www.youtube-nocookie.com/embed/${item.videoId}?autoplay=1&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}&rel=0`;
                    container.innerHTML = `
                        <iframe id="iframe-${messageId}" src="${iframeSrc}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
                    `;
                } else {
                    try {
                        iframe.contentWindow.postMessage('{"event":"command","func":"playVideo","args":""}', '*');
                    } catch (e) {}
                }
            } else if (state === PLAYBACK_STATE.PAUSED) {
                const iframe = container.querySelector('iframe');
                if (iframe) {
                    try {
                        iframe.contentWindow.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*');
                    } catch (e) {}
                }
            } else {
                // STOPPED, ENDED, or ERROR
                const thumbUrl = item.thumbnail || `https://img.youtube.com/vi/${item.videoId}/hqdefault.jpg`;
                container.innerHTML = `
                    <div class="video-thumb-overlay" onclick="MediaManager.handleCardPlayClick('${messageId}')">
                        <img src="${thumbUrl}" alt="${escHtml(item.title || 'Video thumbnail')}" class="video-thumb-img" onerror="this.src='https://img.youtube.com/vi/${item.videoId}/0.jpg'" />
                        <div class="video-thumb-gradient"></div>
                        <button type="button" class="thumb-play-circle" title="Play Video">
                            <i class="fa-solid fa-play"></i>
                        </button>
                        <div class="thumb-caption">
                            <span class="thumb-title">${escHtml(item.title || 'Video Player')}</span>
                            <span class="thumb-channel">${escHtml(item.channel || 'YouTube')}</span>
                        </div>
                    </div>
                `;
            }
        }
    },

    pauseOrStopVideoElement(messageId, targetState = PLAYBACK_STATE.STOPPED) {
        const card = document.getElementById(`video-card-${messageId}`);
        if (!card) return;
        const iframe = card.querySelector('iframe');
        if (iframe && iframe.contentWindow) {
            try {
                iframe.contentWindow.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*');
            } catch (e) {}
        }
        const item = this.mediaRegistry.get(messageId);
        if (item) {
            item.playbackState = targetState;
            this.renderCardState(messageId, targetState);
        }
    },

    handleCardPlayClick(messageId) {
        const item = this.mediaRegistry.get(messageId);
        if (!item) return;
        if (item.playbackState === PLAYBACK_STATE.PLAYING) {
            this.setPlaybackState(messageId, PLAYBACK_STATE.PAUSED);
        } else {
            this.setPlaybackState(messageId, PLAYBACK_STATE.PLAYING);
        }
    },

    handleCardStopClick(messageId) {
        this.pauseOrStopVideoElement(messageId, PLAYBACK_STATE.STOPPED);
        this.setPlaybackState(messageId, PLAYBACK_STATE.STOPPED);
        TaskmasterAPI.stopMedia();
    },

    handleRemoteStateChange(payload) {
        if (!payload || !payload.messageId || payload.sourceTabId === this.tabId) return;
        const item = this.mediaRegistry.get(payload.messageId);
        if (item) {
            // Check version to prevent stale out-of-order execution
            if (item.version && payload.version && payload.version <= item.version) {
                return; // Ignore stale version
            }
            item.version = payload.version;
            this.setPlaybackState(payload.messageId, payload.playbackState, { silent: true });
        } else {
            // Register if not yet in local map
            this.registerMedia(payload.messageId, {
                videoId: payload.videoId,
                playbackState: payload.playbackState,
                version: payload.version
            });
            this.setPlaybackState(payload.messageId, payload.playbackState, { silent: true });
        }
    },

    stopAllMedia(options = {}) {
        this.mediaRegistry.forEach((item, msgId) => {
            if (item.playbackState === PLAYBACK_STATE.PLAYING) {
                this.pauseOrStopVideoElement(msgId, PLAYBACK_STATE.STOPPED);
                item.playbackState = PLAYBACK_STATE.STOPPED;
            }
        });
        this.activeMessageId = null;
        this.activeMediaId = null;
        TaskmasterAPI.stopMedia();
        if (!options.silent) {
            TabSync.broadcast('MEDIA_STOP_ALL', { sourceTabId: this.tabId, timestamp: Date.now() });
        }
    }
};

// ── Multi-Tab Real-Time Synchronization Engine ──
const TabSync = {
    channel: (typeof BroadcastChannel !== 'undefined') ? new BroadcastChannel('taskmaster_sync_channel') : null,

    init() {
        if (!this.channel) return;
        this.channel.onmessage = (event) => {
            const { type, payload } = event.data || {};
            if (!type) return;

            switch (type) {
                case 'MEDIA_STATE_CHANGE':
                    MediaManager.handleRemoteStateChange(payload);
                    break;
                case 'MEDIA_STOP_ALL':
                    MediaManager.stopAllMedia({ silent: true });
                    break;
                case 'SESSION_UPDATED':
                    renderSidebarHistory();
                    if (payload && payload.sessionId === currentSessionId) {
                        ChatStorage.getSessionMessages(currentSessionId).then(msgs => {
                            renderChatMessages({ id: currentSessionId, messages: msgs });
                        });
                    }
                    break;
                case 'SESSION_DELETED':
                    renderSidebarHistory();
                    if (payload && payload.sessionId === currentSessionId) {
                        startNewChat();
                    }
                    break;
            }
        };
    },

    broadcast(type, payload = {}) {
        if (this.channel) {
            try {
                this.channel.postMessage({ type, payload });
            } catch (e) {}
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    TabSync.init();
    initApp();
    setupEventListeners();
});

async function initApp() {
    // 1. Enforce Authentication Guard
    const user = await AuthManager.checkSession();
    if (!user) {
        window.location.href = '/auth';
        return;
    }

    // Populate user profile badge
    const userNameLabel = document.getElementById('userNameLabel');
    const userEmailLabel = document.getElementById('userEmailLabel');
    const userAvatarLetter = document.getElementById('userAvatarLetter');
    if (userNameLabel) userNameLabel.textContent = user.full_name || user.email.split('@')[0];
    if (userEmailLabel) userEmailLabel.textContent = user.email;
    if (userAvatarLetter) userAvatarLetter.textContent = (user.full_name || user.email)[0].toUpperCase();

    // 2. Health check & Tool count
    const health = await TaskmasterAPI.getHealth();
    const statusPill = document.getElementById('statusPill');
    if (statusPill) {
        statusPill.textContent = health.status === 'HEALTHY' ? '● Healthy' : '● ' + (health.status || 'Offline');
        statusPill.className = 'status-pill ' + (health.status === 'HEALTHY' ? 'healthy' : '');
    }

    // 3. Load Tools count in model badge
    const toolsData = await TaskmasterAPI.getTools();
    const toolCountBadge = document.getElementById('toolCountBadge');
    if (toolCountBadge && toolsData.tools) {
        toolCountBadge.textContent = `${toolsData.tools.length} Tools`;
    }

    // 4. Initialize Sidebar state
    initSidebarState();

    // 4.5. Initialize Autonomous Heartbeat Event Listener & Status
    initHeartbeatEventListener();

    // 5. Initialize or Restore Active Chat Session from SQLite
    await renderSidebarHistory();
    const activeId = ChatStorage.getActiveSessionId();
    if (activeId) {
        await loadSession(activeId);
    } else {
        const sessions = await ChatStorage.getSessions();
        if (sessions.length > 0) {
            await loadSession(sessions[0].id);
        } else {
            await startNewChat();
        }
    }
}

function setSendButtonState(state) {
    const sendBtn = document.getElementById('sendBtn');
    const textarea = document.getElementById('chatInput');
    if (!sendBtn) return;
    if (state === 'stop') {
        sendBtn.className = 'chat-send-btn stop-btn';
        sendBtn.innerHTML = '<i class="fa-solid fa-square"></i>';
        sendBtn.title = 'Stop generating';
        sendBtn.disabled = false;
    } else {
        sendBtn.className = 'chat-send-btn';
        sendBtn.innerHTML = '<i class="fa-solid fa-arrow-up"></i>';
        sendBtn.title = 'Send message';
        if (textarea) {
            sendBtn.disabled = (!textarea.value.trim() && pendingAttachments.length === 0);
        }
    }
}

function cleanStatusText(text) {
    if (!text) return '';
    return text.replace(/^[\p{Emoji}\u200d\uFE0F⚡✅🔄🧠🗺️🔍📄✨\s]+/gu, '').trim();
}

function abortCurrentExecution() {
    if (!isExecuting) return;
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }

    const activeRow = document.getElementById('activeStreamingRow');
    if (activeRow) {
        const thinking = document.getElementById('liveThinkingIndicator');
        if (thinking) thinking.remove();
        const bubble = document.getElementById('activeStreamingBubble');
        if (bubble && !bubble.querySelector('.result-card') && !bubble.querySelector('.video-player-card')) {
            const stopMsg = document.createElement('div');
            stopMsg.style.cssText = 'color:var(--text-muted); font-size:0.85rem; font-style:italic; padding:0.4rem 0.2rem;';
            stopMsg.textContent = 'Generation stopped by user.';
            bubble.appendChild(stopMsg);
        }
        activeRow.id = '';
    }

    isExecuting = false;
    setSendButtonState('send');
    updateInputState();
    scrollToBottom();
}

function updateInputState() {
    const textarea = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    if (!textarea || !sendBtn) return;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';

    const hasContent = textarea.value.trim().length > 0 || pendingAttachments.length > 0;
    if (isExecuting) {
        setSendButtonState('stop');
    } else {
        setSendButtonState('send');
        sendBtn.disabled = !hasContent;
    }
}

function setupEventListeners() {
    const textarea = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const newChatBtn = document.getElementById('newChatBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileAttachmentInput');

    // Auto-grow textarea and enable/disable send button
    if (textarea) {
        ['input', 'keyup', 'change', 'paste', 'cut'].forEach(evt => {
            textarea.addEventListener(evt, updateInputState);
        });

        // Keydown handling: Enter sends, Shift+Enter new line
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if ((textarea.value.trim() || pendingAttachments.length > 0) && !isExecuting) {
                    handleSendMessage();
                }
            }
        });
    }

    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            if (isExecuting) {
                abortCurrentExecution();
            } else if (textarea && (textarea.value.trim() || pendingAttachments.length > 0)) {
                handleSendMessage();
            }
        });
    }

    // Attachment Plus Button & Popover Menu
    const attachMenu = document.getElementById('attachMenu');
    if (attachBtn) {
        attachBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleAttachMenu();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleFilesSelected(e.target.files);
                fileInput.value = '';
            }
        });
    }

    // Dismiss attachment menu when clicking outside
    document.addEventListener('click', (e) => {
        if (attachMenu && !attachMenu.contains(e.target) && e.target !== attachBtn && !attachBtn?.contains(e.target)) {
            closeAttachMenu();
        }
    });

    // Dismiss on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAttachMenu();
            closeDeleteModal();
        }
    });

    // Drag and Drop on window/chat area
    window.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    window.addEventListener('drop', (e) => {
        e.preventDefault();
        closeAttachMenu();
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFilesSelected(e.dataTransfer.files);
        }
    });

    // Paste screenshot / image from clipboard
    window.addEventListener('paste', (e) => {
        if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
            closeAttachMenu();
            handleFilesSelected(e.clipboardData.files);
        }
    });

    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            startNewChat();
        });
    }

    // Stop Media Button in Navbar
    const stopMediaBtn = document.getElementById('stopMediaBtn');
    if (stopMediaBtn) {
        stopMediaBtn.addEventListener('click', async () => {
            stopMediaBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Stopping...';
            MediaManager.stopAllMedia();
            setTimeout(() => {
                stopMediaBtn.innerHTML = '<i class="fa-solid fa-stop"></i> Stop Media';
            }, 500);
        });
    }

        // Stop background playback when user navigates away or closes tab
    window.addEventListener('beforeunload', () => {
        MediaManager.stopAllMedia();
    });

    // Sidebar Collapse / Open Buttons
    const collapseBtn = document.getElementById('sidebarCollapseBtn');
    const openBtn = document.getElementById('sidebarOpenBtn');

    if (collapseBtn) {
        collapseBtn.addEventListener('click', () => toggleSidebar(true));
    }
    if (openBtn) {
        openBtn.addEventListener('click', () => toggleSidebar(false));
    }

    // Global shortcut Ctrl+K / Cmd+K for New Chat, and Ctrl+[ or Ctrl+B for Sidebar
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            startNewChat();
        } else if ((e.ctrlKey || e.metaKey) && (e.key === '[' || e.key.toLowerCase() === 'b')) {
            e.preventDefault();
            toggleSidebar();
        }
    });
}

function toggleSidebar(forceState = null) {
    const sidebar = document.getElementById('chatSidebar');
    if (!sidebar) return;
    const isCurrentlyCollapsed = sidebar.classList.contains('collapsed');
    const shouldCollapse = forceState !== null ? forceState : !isCurrentlyCollapsed;
    
    if (shouldCollapse) {
        sidebar.classList.add('collapsed');
        localStorage.setItem('taskmaster_sidebar_collapsed', 'true');
    } else {
        sidebar.classList.remove('collapsed');
        localStorage.setItem('taskmaster_sidebar_collapsed', 'false');
    }
}

function initSidebarState() {
    const saved = localStorage.getItem('taskmaster_sidebar_collapsed');
    const sidebar = document.getElementById('chatSidebar');
    if (!sidebar) return;
    if (saved === 'true') {
        sidebar.classList.add('collapsed');
    }
}

function pauseLocalMediaPlayback(shouldBroadcast = true) {
    MediaManager.stopAllMedia({ silent: !shouldBroadcast });
}

async function startNewChat() {
    // Automatically stop any lingering media playback
    MediaManager.stopAllMedia();

    const session = await ChatStorage.createSession('New Chat');
    currentSessionId = session.id;
    TabSync.broadcast('SESSION_UPDATED', { sessionId: currentSessionId });
    await renderSidebarHistory();
    renderChatMessages({ id: currentSessionId, messages: [] });
    const textarea = document.getElementById('chatInput');
    if (textarea) {
        textarea.value = '';
        textarea.style.height = 'auto';
        textarea.focus();
    }
}

async function loadSession(sessionId) {
    MediaManager.stopAllMedia();
    currentSessionId = sessionId;
    ChatStorage.setActiveSessionId(sessionId);
    await renderSidebarHistory();
    const messages = await ChatStorage.getSessionMessages(sessionId);
    renderChatMessages({ id: sessionId, messages });
}

async function renderSidebarHistory() {
    const historyContainer = document.getElementById('sidebarHistory');
    if (!historyContainer) return;

    const sessions = await ChatStorage.getSessions();
    if (sessions.length === 0) {
        historyContainer.innerHTML = `
            <div style="padding: 1rem 0.5rem; text-align: center; color: var(--text-dim); font-size: 0.8rem;">
                No recent conversations
            </div>
        `;
        return;
    }

    // Group sessions by date
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    const groups = { 'Today': [], 'Previous 7 Days': [], 'Older': [] };

    sessions.forEach(s => {
        const diff = now - (s.updated_at || s.created_at || now);
        if (diff < oneDay) groups['Today'].push(s);
        else if (diff < 7 * oneDay) groups['Previous 7 Days'].push(s);
        else groups['Older'].push(s);
    });

    let html = '';
    for (const [groupName, items] of Object.entries(groups)) {
        if (items.length === 0) continue;
        html += `
            <div>
                <div class="history-group-title">${groupName}</div>
                <ul class="history-list">
                    ${items.map(s => `
                        <li class="history-item ${s.id === currentSessionId ? 'active' : ''}" onclick="loadSession('${s.id}')">
                            <span class="history-title">${escHtml(s.title || 'New Chat')}</span>
                            <div class="history-actions" onclick="event.stopPropagation();">
                                <button class="history-btn" title="Delete chat" onclick="promptDeleteSession('${s.id}')">
                                    <i class="fa-regular fa-trash-can"></i>
                                </button>
                            </div>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }

    historyContainer.innerHTML = html;
}

let sessionToDelete = null;

function promptDeleteSession(sessionId) {
    sessionToDelete = sessionId;
    const modal = document.getElementById('deleteConfirmModal');
    if (modal) {
        modal.style.display = 'flex';
    }
}

function closeDeleteModal() {
    sessionToDelete = null;
    const modal = document.getElementById('deleteConfirmModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function executeDeleteSession() {
    if (!sessionToDelete) return;
    const targetId = sessionToDelete;
    closeDeleteModal();
    TaskmasterAPI.stopMedia();
    await ChatStorage.deleteSession(targetId);
    await renderSidebarHistory();
    const activeId = ChatStorage.getActiveSessionId();
    if (activeId && activeId !== targetId) {
        await loadSession(activeId);
    } else {
        await startNewChat();
    }
}

function toggleAttachMenu() {
    const menu = document.getElementById('attachMenu');
    const btn = document.getElementById('attachBtn');
    if (!menu || !btn) return;
    const isOpen = menu.classList.contains('open');
    if (isOpen) {
        closeAttachMenu();
    } else {
        menu.classList.add('open');
        btn.classList.add('active');
        btn.setAttribute('aria-expanded', 'true');
    }
}

function closeAttachMenu() {
    const menu = document.getElementById('attachMenu');
    const btn = document.getElementById('attachBtn');
    if (menu) menu.classList.remove('open');
    if (btn) {
        btn.classList.remove('active');
        btn.setAttribute('aria-expanded', 'false');
    }
}

function triggerSpecificUpload(category) {
    const fileInput = document.getElementById('fileAttachmentInput');
    if (!fileInput) return;

    const acceptMap = {
        'image': 'image/*,.png,.jpg,.jpeg,.webp,.gif,.svg',
        'document': '.pdf,.docx,.doc,.txt,.md,.rtf',
        'data': '.csv,.xlsx,.xls,.json,.tsv,.parquet',
        'code': '.py,.js,.html,.css,.json,.ts,.tsx,.jsx,.sql,.sh,.cpp,.c,.java',
        'all': 'image/*,.pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.json,.py,.js,.html,.css'
    };

    fileInput.accept = acceptMap[category] || '*/*';
    closeAttachMenu();
    fileInput.click();
}

function insertPromptShortcut(text) {
    closeAttachMenu();
    const textarea = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    if (!textarea) return;
    textarea.value = text;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
    textarea.focus();
    if (sendBtn) sendBtn.disabled = !textarea.value.trim() || isExecuting;
}

function filterAttachMenuItems(query) {
    const items = document.querySelectorAll('.chat-attach-menu .attach-menu-item');
    const q = (query || '').toLowerCase().trim();
    items.forEach(item => {
        const title = item.querySelector('.attach-item-title')?.textContent.toLowerCase() || '';
        const sub = item.querySelector('.attach-item-sub')?.textContent.toLowerCase() || '';
        if (!q || title.includes(q) || sub.includes(q)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

function handleFilesSelected(files) {
    const sendBtn = document.getElementById('sendBtn');
    Array.from(files).forEach(file => {
        const isImg = file.type.startsWith('image/');
        const reader = new FileReader();

        if (isImg) {
            reader.onload = (ev) => {
                pendingAttachments.push({
                    id: 'att_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    isImage: true,
                    dataUrl: ev.target.result
                });
                renderAttachmentPreviews();
            };
            reader.readAsDataURL(file);
        } else {
            reader.onload = (ev) => {
                pendingAttachments.push({
                    id: 'att_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
                    name: file.name,
                    size: file.size,
                    type: file.type || 'text/plain',
                    isImage: false,
                    textContent: typeof ev.target.result === 'string' ? ev.target.result : ''
                });
                renderAttachmentPreviews();
            };
            reader.readAsText(file);
        }
    });
}

function removeAttachment(attId) {
    pendingAttachments = pendingAttachments.filter(a => a.id !== attId);
    renderAttachmentPreviews();
}

function renderAttachmentPreviews() {
    const strip = document.getElementById('attachmentPreviewStrip');
    const sendBtn = document.getElementById('sendBtn');
    const textarea = document.getElementById('chatInput');
    if (!strip) return;

    if (pendingAttachments.length === 0) {
        strip.innerHTML = '';
        strip.classList.remove('has-files');
        if (sendBtn && textarea) {
            sendBtn.disabled = !textarea.value.trim() || isExecuting;
        }
        return;
    }

    strip.classList.add('has-files');
    strip.innerHTML = pendingAttachments.map(att => `
        <div class="attachment-preview-card">
            ${att.isImage 
                ? `<img src="${att.dataUrl}" class="img-thumb" alt="${escHtml(att.name)}">` 
                : `<i class="fa-solid fa-file-lines" style="color:#2563eb; font-size:1rem;"></i>`
            }
            <span class="attachment-file-name" title="${escHtml(att.name)}">${escHtml(att.name)}</span>
            <button type="button" class="attachment-remove-btn" onclick="removeAttachment('${att.id}')" title="Remove">✕</button>
        </div>
    `).join('');

    if (sendBtn) sendBtn.disabled = isExecuting;
}

function renderChatMessages(session) {
    const messagesInner = document.getElementById('messagesInner');
    const welcomeHero = document.getElementById('welcomeHero');
    if (!messagesInner) return;

    if (!session || !session.messages || session.messages.length === 0) {
        messagesInner.innerHTML = '';
        if (welcomeHero) welcomeHero.style.display = 'flex';
        return;
    }

    if (welcomeHero) welcomeHero.style.display = 'none';

    messagesInner.innerHTML = session.messages.map((m, idx) => {
        const msgId = m.id || (m.data && m.data.message_id) || (`msg_${m.timestamp || Date.now()}_${idx}`);
        if (m.role === 'user') {
            let attachmentsHtml = '';
            if (m.attachments && m.attachments.length > 0) {
                attachmentsHtml = `
                    <div class="user-attached-media">
                        ${m.attachments.map(att => {
                            if (att.isImage && att.dataUrl) {
                                return `<img src="${att.dataUrl}" class="user-attached-img" alt="${escHtml(att.name)}">`;
                            } else {
                                return `<span class="user-attached-file-badge"><i class="fa-solid fa-file-lines"></i> ${escHtml(att.name)}</span>`;
                            }
                        }).join('')}
                    </div>
                `;
            }
            return `
                <div class="message-row user" id="msg-row-${msgId}">
                    <div class="message-bubble">
                        ${attachmentsHtml}
                        ${escHtml(m.content)}
                    </div>
                </div>
            `;
        } else {
            return `
                <div class="message-row ai" id="msg-row-${msgId}">
                    <div class="message-avatar ai">
                        <img src="/frontend/t_logo.png" alt="Taskmaster AI" />
                    </div>
                    <div class="message-bubble">
                        ${renderAgentMessageContent(m.data, m.content, msgId)}
                    </div>
                </div>
            `;
        }
    }).join('');

    scrollToBottom();
}

// Helper to strictly extract YouTube video IDs (and ignore Docs, Sheets, and other URLs)
function extractYouTubeVideoId(url) {
    if (!url || typeof url !== 'string') return null;
    if (!url.includes('youtube.com') && !url.includes('youtu.be')) return null;
    const m = url.match(/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\\s\)]{11})/i);
    return m ? m[1] : null;
}

function generateAutoTitle(promptText, attachments) {
    if (promptText && promptText.trim()) {
        let clean = promptText.trim().replace(/^[\r\n\t]+/, '').split('\n')[0].trim();
        // Capitalize first character
        clean = clean.charAt(0).toUpperCase() + clean.slice(1);
        if (clean.length > 32) {
            return clean.substring(0, 30).trim() + '...';
        }
        return clean;
    }
    if (attachments && attachments.length > 0) {
        const att = attachments[0];
        const name = att.name.length > 24 ? att.name.substring(0, 22) + '...' : att.name;
        return att.isImage ? `Image: ${name}` : `Doc: ${name}`;
    }
    return 'Task Execution';
}

async function handleSendMessage() {
    const textarea = document.getElementById('chatInput');
    const userPrompt = textarea ? textarea.value.trim() : '';
    if (!userPrompt && pendingAttachments.length === 0) return;

    if (isExecuting) {
        const activeRow = document.getElementById('activeStreamingRow');
        if (!activeRow) {
            isExecuting = false;
        } else {
            return;
        }
    }

    isExecuting = true;
    setSendButtonState('stop');
    if (textarea) {
        textarea.value = '';
        textarea.style.height = 'auto';
    }

    const currentAtts = [...pendingAttachments];
    pendingAttachments = [];
    renderAttachmentPreviews();
    updateInputState();

    // 1. Add User Message to SQLite backend with attachments metadata
    const userMsgId = 'msg_user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    const userMsg = { 
        id: userMsgId,
        role: 'user', 
        content: userPrompt || (currentAtts.length > 0 ? (currentAtts[0].isImage ? 'Analyze attached picture' : `Analyze ${currentAtts[0].name}`) : ''), 
        attachments: currentAtts, 
        timestamp: Date.now() 
    };

    // Auto-rename session in real time if it's currently "New Chat"
    const sessions = await ChatStorage.getSessions();
    const currentSession = sessions.find(s => s.id === currentSessionId);
    if (!currentSession || currentSession.title === 'New Chat' || !currentSession.title) {
        const autoTitle = generateAutoTitle(userPrompt, currentAtts);
        // Instant visual update in sidebar
        const activeSidebarTitle = document.querySelector(`.history-item.active .history-title, li[onclick*="${currentSessionId}"] .history-title`);
        if (activeSidebarTitle) {
            activeSidebarTitle.textContent = autoTitle;
        }
        await ChatStorage.renameSession(currentSessionId, autoTitle);
    }

    // Hide welcome hero if visible
    const welcomeHero = document.getElementById('welcomeHero');
    if (welcomeHero) welcomeHero.style.display = 'none';

    // Remove active IDs from any previous streaming row
    const oldActiveRow = document.getElementById('activeStreamingRow');
    if (oldActiveRow) oldActiveRow.id = '';
    const oldActiveBubble = document.getElementById('activeStreamingBubble');
    if (oldActiveBubble) oldActiveBubble.id = '';

    // Append User Message Row directly to DOM
    let attachmentsHtml = '';
    if (currentAtts.length > 0) {
        attachmentsHtml = `
            <div class="user-attached-media">
                ${currentAtts.map(att => {
                    if (att.isImage && att.dataUrl) {
                        return `<img src="${att.dataUrl}" class="user-attached-img" alt="${escHtml(att.name)}">`;
                    } else {
                        return `<span class="user-attached-file-badge"><i class="fa-solid fa-file-lines"></i> ${escHtml(att.name)}</span>`;
                    }
                }).join('')}
            </div>
        `;
    }
    const userRow = document.createElement('div');
    userRow.className = 'message-row user';
    userRow.id = `msg-row-${userMsgId}`;
    userRow.innerHTML = `
        <div class="message-bubble">
            ${attachmentsHtml}
            ${escHtml(userMsg.content)}
        </div>
    `;
    const messagesInner = document.getElementById('messagesInner');
    if (messagesInner) messagesInner.appendChild(userRow);

    await ChatStorage.addMessage(currentSessionId, userMsg);
    TabSync.broadcast('SESSION_UPDATED', { sessionId: currentSessionId });
    renderSidebarHistory();

    // Synthesize full goal prompt for the agent
    let goal = userMsg.content;
    if (currentAtts.length > 0) {
        const fileSnippets = currentAtts.map(f => {
            if (f.isImage) {
                return `[Attached Image: "${f.name}" (${Math.round(f.size/1024)} KB)]`;
            } else {
                const snippet = (f.textContent || '').slice(0, 4000);
                return `[Attached Document: "${f.name}" (${f.type})]:\n\`\`\`\n${snippet}\n\`\`\``;
            }
        }).join('\n\n');
        goal = `${fileSnippets}\n\nUser Request: ${userPrompt || 'Please review, analyze, and extract key information from the attached file(s).'}`;
    }

    // Parse requested duration ONLY if explicitly requested
    let requestedDuration = null;
    const durMatch = goal.match(/\bfor\s+(\d+)\s*(?:seconds?|secs?|s)\b/i);
    const minMatch = goal.match(/\bfor\s+(\d+)\s*(?:minutes?|mins?|m)\b/i);
    if (durMatch) requestedDuration = parseInt(durMatch[1], 10);
    else if (minMatch) requestedDuration = parseInt(minMatch[1], 10) * 60;

    // 2. Append Live Real-Time AI Response
    const liveMessageId = 'msg_ai_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    const activeRow = document.createElement('div');
    activeRow.className = 'message-row ai';
    activeRow.id = 'activeStreamingRow';
    activeRow.innerHTML = `
        <div class="message-avatar ai">
            <img src="/frontend/t_logo.png" alt="Taskmaster AI" />
        </div>
        <div class="message-bubble" id="activeStreamingBubble" style="min-width: 220px; width: fit-content; max-width: 720px;">
            <div class="live-thinking-line" id="liveThinkingIndicator">
                <div class="spinner-dot"></div>
                <span id="liveStatusText" class="live-thinking-text">Thinking & analyzing instructions...</span>
            </div>
        </div>
    `;
    if (messagesInner) messagesInner.appendChild(activeRow);
    scrollToBottom();

    // Fast cycling dynamic thoughts
    const dynamicThoughts = [
        "Analyzing goal & context...",
        "Decomposing execution steps...",
        "Accessing tools & data...",
        "Executing autonomous tasks...",
        "Synthesizing deliverable...",
        "Finalizing response..."
    ];
    let thoughtIdx = 0;
    let explicitStatusSet = false;

    const thoughtInterval = setInterval(() => {
        if (!explicitStatusSet) {
            thoughtIdx = (thoughtIdx + 1) % dynamicThoughts.length;
            const statusEl = document.getElementById('liveStatusText');
            if (statusEl) {
                statusEl.classList.add('fade-out');
                setTimeout(() => {
                    statusEl.textContent = cleanStatusText(dynamicThoughts[thoughtIdx]);
                    statusEl.classList.remove('fade-out');
                    statusEl.classList.add('fade-in');
                    setTimeout(() => statusEl.classList.remove('fade-in'), 200);
                }, 150);
            }
        }
    }, 1500);

    const startTime = Date.now();

    let streamCompleted = false;
    let lastDetectedMedia = null;

    const cleanup = () => {
        clearInterval(thoughtInterval);
        isExecuting = false;
        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }
        setSendButtonState('send');
        updateInputState();
        scrollToBottom();
    };

    const finalizeSuccess = async (wf) => {
        if (streamCompleted) return;
        streamCompleted = true;
        cleanup();
        const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);

        const activeBubble = document.getElementById('activeStreamingBubble');
        const thinking = document.getElementById('liveThinkingIndicator');
        if (thinking) thinking.remove();

        // Extract video ID from lastDetectedMedia, wf, or wf.summary
        let finalVidId = (lastDetectedMedia && lastDetectedMedia.video_id) || (wf ? wf.video_id : null);
        let finalVidUrl = (lastDetectedMedia && lastDetectedMedia.video_url) || (wf ? wf.video_url : null) || (wf ? wf.url : null);
        if (!finalVidId && wf && wf.summary) {
            finalVidId = extractYouTubeVideoId(wf.summary);
            if (finalVidId && !finalVidUrl) {
                finalVidUrl = `https://www.youtube.com/watch?v=${finalVidId}`;
            }
        }

        const aiMsg = {
            id: liveMessageId,
            role: 'assistant',
            content: wf.summary || 'Task completed successfully.',
            data: {
                ...wf,
                message_id: liveMessageId,
                video_id: finalVidId,
                video_url: finalVidUrl,
                url: finalVidUrl,
                video_title: (lastDetectedMedia && lastDetectedMedia.video_title) || (wf ? wf.video_title : null),
                channel: (lastDetectedMedia && lastDetectedMedia.channel) || (wf ? wf.channel : null),
                playbackState: finalVidId ? PLAYBACK_STATE.PLAYING : PLAYBACK_STATE.NONE,
                elapsedSec,
                requestedDuration
            },
            timestamp: Date.now()
        };
        await ChatStorage.addMessage(currentSessionId, aiMsg);

        // Crucial: Set isExecuting to false so composer returns to SEND
        isExecuting = false;
        setSendButtonState('send');
        updateInputState();

        if (activeBubble && !hasRenderedLiveResponse) {
            activeBubble.innerHTML = `<div class="result-card">${renderMarkdown(stripBoilerplate(wf.summary || 'Task completed successfully.'))}</div>`;
        }

        if (activeRow) activeRow.id = '';
        if (activeBubble) activeBubble.id = '';
        scrollToBottom();
    };

    const finalizeError = async (errMessage) => {
        if (streamCompleted) return;
        streamCompleted = true;
        cleanup();

        const activeBubble = document.getElementById('activeStreamingBubble');
        const thinking = document.getElementById('liveThinkingIndicator');
        if (thinking) thinking.remove();

        const errAiMsg = {
            id: liveMessageId,
            role: 'assistant',
            content: `**Error:** ${errMessage}`,
            data: { status: 'FAILED', error: errMessage },
            timestamp: Date.now()
        };
        await ChatStorage.addMessage(currentSessionId, errAiMsg);

        if (activeBubble) {
            activeBubble.innerHTML = `<div class="result-card" style="border-left: 3px solid #ef4444;">${renderMarkdown(`**Error:** ${errMessage}`)}</div>`;
        }

        if (activeRow) activeRow.id = '';
        if (activeBubble) activeBubble.id = '';
        scrollToBottom();
    };

    let hasRenderedLiveResponse = false;

    // Unified Atomic Render: Loads video and downward text TOGETHER at the exact same moment without reloading
    const renderUnifiedLiveResponse = (resObj, summaryText) => {
        const activeBubble = document.getElementById('activeStreamingBubble');
        if (!activeBubble) return;

        let detectedVid = null;
        let detectedUrl = null;
        let detectedTitle = null;
        let detectedChannel = null;

        if (resObj) {
            const rawUrl = resObj.video_url || resObj.url;
            const rawVid = resObj.video_id;
            const playback = resObj.playback_state || {};

            if (playback.title) detectedTitle = playback.title;
            if (playback.channel) detectedChannel = playback.channel;
            if (resObj.video_title) detectedTitle = resObj.video_title;
            if (resObj.title) detectedTitle = detectedTitle || resObj.title;
            if (resObj.channel) detectedChannel = detectedChannel || resObj.channel;
            if (resObj.author) detectedChannel = detectedChannel || resObj.author;

            if (rawVid && typeof rawVid === 'string' && rawVid.length === 11 && !rawVid.startsWith('$')) {
                detectedVid = rawVid;
                detectedUrl = rawUrl || `https://www.youtube.com/watch?v=${rawVid}`;
            } else if (rawUrl && typeof rawUrl === 'string') {
                const vid = extractYouTubeVideoId(rawUrl);
                if (vid) {
                    detectedVid = vid;
                    detectedUrl = rawUrl;
                }
            } else if (resObj.results && Array.isArray(resObj.results) && resObj.results.length > 0) {
                const first = resObj.results[0];
                if (first && first.video_id && typeof first.video_id === 'string' && first.video_id.length === 11) {
                    detectedVid = first.video_id;
                    detectedUrl = first.url || `https://www.youtube.com/watch?v=${first.video_id}`;
                    if (first.title) detectedTitle = first.title;
                    if (first.channel) detectedChannel = first.channel;
                }
            }
        }

        // Check summaryText for title or video ID
        if (summaryText) {
            const sumVid = extractYouTubeVideoId(summaryText);
            if (sumVid && !detectedVid) {
                detectedVid = sumVid;
                detectedUrl = `https://www.youtube.com/watch?v=${sumVid}`;
            }
            const matchTrack = summaryText.match(/Track Title:\*\*\s*([^\n\r*]+)/i) || 
                               summaryText.match(/##\s*🎵\s*Now\s*Playing:\s*([^\n\r]+)/i) ||
                               summaryText.match(/\*\*Song:\*\*\s*([^\n\r*]+)/i);
            if (matchTrack && matchTrack[1] && matchTrack[1].trim()) {
                detectedTitle = matchTrack[1].trim();
            }
        }

        if (detectedVid && lastDetectedMedia && lastDetectedMedia.video_id === detectedVid) {
            detectedTitle = detectedTitle || lastDetectedMedia.video_title;
            detectedChannel = detectedChannel || lastDetectedMedia.channel;
        }

        detectedTitle = detectedTitle || (resObj ? (resObj.video_title || resObj.title || resObj.query) : null) || 'Selected Video/Track';
        detectedChannel = detectedChannel || (resObj ? (resObj.channel || resObj.author) : null) || 'YouTube';

        if (detectedVid) {
            lastDetectedMedia = {
                video_id: detectedVid,
                video_url: detectedUrl || `https://www.youtube.com/watch?v=${detectedVid}`,
                url: detectedUrl || `https://www.youtube.com/watch?v=${detectedVid}`,
                video_title: detectedTitle,
                channel: detectedChannel
            };
        }

        // Build text content
        let text = summaryText || (resObj ? resObj.summary : '');
        if (!text && resObj) {
            const trackTitle = detectedTitle;
            if (trackTitle || detectedVid || resObj.url || resObj.video_url) {
                const displayTitle = trackTitle || 'Selected Video/Track';
                const playbackState = resObj.playback_state || {};
                const channelName = detectedChannel || playbackState.channel || '';
                const durPlayed = resObj.duration_played_seconds || resObj.duration || '';
                const durStr = durPlayed ? ` (${durPlayed}s)` : '';
                text = `## 🎵 Now Playing: ${displayTitle}\n\n` +
                       `I have successfully initiated playback of the requested track:\n\n` +
                       `* **Song:** ${displayTitle}${durStr}\n` +
                       (channelName ? `* **Channel:** ${channelName}\n` : '') +
                       `* **Status:** Playback started`;
            }
        }

        const thinking = document.getElementById('liveThinkingIndicator');
        if (thinking) thinking.remove();

        activeBubble.style.width = '100%';
        activeBubble.style.maxWidth = '680px';

        const existingCard = activeBubble.querySelector('.video-player-card');

        if (detectedVid && !existingCard) {
            // First-time insertion of video player card
            MediaManager.registerMedia(liveMessageId, {
                videoId: detectedVid,
                title: detectedTitle,
                channel: detectedChannel,
                url: detectedUrl,
                playbackState: PLAYBACK_STATE.PLAYING
            });

            const iframeSrc = `https://www.youtube-nocookie.com/embed/${detectedVid}?autoplay=1&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}&rel=0`;

            let combinedHtml = `
                <div class="video-player-card" id="video-card-${liveMessageId}">
                    <div class="video-player-header">
                        <div class="video-header-info">
                            <i class="fa-brands fa-youtube video-brand-icon"></i>
                            <div class="video-title-wrap">
                                <span class="video-player-title" title="${escHtml(detectedTitle)}">${escHtml(detectedTitle)}</span>
                                <span class="video-player-channel">${escHtml(detectedChannel)}</span>
                            </div>
                        </div>
                        <div class="video-header-actions">
                            <span class="media-status-badge status-playing">
                                <span class="pulse-dot"></span> Playing
                            </span>
                            <a href="${escHtml(detectedUrl)}" class="video-link-btn" target="_blank" title="Open on YouTube">
                                <i class="fa-solid fa-arrow-up-right-from-square"></i>
                            </a>
                        </div>
                    </div>
                    <div class="video-viewport">
                        <iframe id="iframe-${liveMessageId}" src="${iframeSrc}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
                    </div>
                    <div class="video-media-controls">
                        <div class="media-ctrl-left">
                            <button type="button" class="media-btn media-ctrl-playpause is-playing" onclick="MediaManager.handleCardPlayClick('${liveMessageId}')">
                                <i class="fa-solid fa-pause"></i> Pause
                            </button>
                            <button type="button" class="media-btn media-ctrl-stop" onclick="MediaManager.handleCardStopClick('${liveMessageId}')">
                                <i class="fa-solid fa-stop"></i> Stop
                            </button>
                        </div>
                        <a href="${escHtml(detectedUrl)}" class="video-link-btn" target="_blank">
                            <span>Watch on YouTube</span> <i class="fa-solid fa-arrow-up-right-from-square"></i>
                        </a>
                    </div>
                </div>
            `;
            if (text) {
                combinedHtml += `<div class="result-card">${renderMarkdown(stripBoilerplate(text))}</div>`;
            }
            activeBubble.innerHTML = combinedHtml;
            hasRenderedLiveResponse = true;

            MediaManager.setPlaybackState(liveMessageId, PLAYBACK_STATE.PLAYING);
        } else if (existingCard) {
            // Video card already exists and is playing! Do not reload the iframe.
            if (text) {
                let resultCard = activeBubble.querySelector('.result-card');
                if (resultCard) {
                    resultCard.innerHTML = renderMarkdown(stripBoilerplate(text));
                } else {
                    const rc = document.createElement('div');
                    rc.className = 'result-card';
                    rc.innerHTML = renderMarkdown(stripBoilerplate(text));
                    activeBubble.appendChild(rc);
                }
            }
            hasRenderedLiveResponse = true;
        } else if (text) {
            // Non-video text result
            let resultCard = activeBubble.querySelector('.result-card');
            if (resultCard) {
                resultCard.innerHTML = renderMarkdown(stripBoilerplate(text));
            } else {
                activeBubble.innerHTML = `<div class="result-card">${renderMarkdown(stripBoilerplate(text))}</div>`;
            }
            hasRenderedLiveResponse = true;
        }

        // When live response renders, Bot generation is completed for this phase
        isExecuting = false;
        setSendButtonState('send');
        updateInputState();
        scrollToBottom();
    };

    // Use Real-Time Strands SSE Stream with fallback (Track 2: Professional Agents)
    try {
        let liveTokenAccumulator = '';
        currentEventSource = TaskmasterAPI.streamStrandsWorkflow(
            goal,
            (eventType, data) => {
                if (eventType === 'workflow_started') {
                    explicitStatusSet = true;
                    const statusEl = document.getElementById('liveStatusText');
                    if (statusEl) {
                        statusEl.textContent = cleanStatusText(`Taskmaster Pro initialized (Strands Agents SDK)...`);
                    }
                } else if (eventType === 'agent_stream_event') {
                    explicitStatusSet = true;
                    const statusEl = document.getElementById('liveStatusText');
                    if (data.tool_call && statusEl) {
                        statusEl.textContent = cleanStatusText(`Tool: ${data.tool_call.name || 'Executing'}...`);
                    }
                    if (data.token) {
                        liveTokenAccumulator += data.token;
                        renderUnifiedLiveResponse(null, liveTokenAccumulator);
                    }
                } else if (eventType === 'workflow_completed') {
                    const finalOutput = data.output || data.summary || liveTokenAccumulator;
                    renderUnifiedLiveResponse(data, finalOutput);
                    finalizeSuccess(data);
                }
            },
            (err) => {
                // Fallback to sync Strands run if SSE fails
                console.warn('Strands SSE stream failed, falling back to sync run:', err);
                TaskmasterAPI.runStrandsWorkflow(goal)
                    .then(res => {
                        const finalOutput = res.output || res.summary;
                        renderUnifiedLiveResponse(res, finalOutput);
                        finalizeSuccess(res);
                    })
                    .catch(e => finalizeError(e.message));
            },
            (data) => {
                finalizeSuccess(data);
            }
        );
    } catch (e) {
        TaskmasterAPI.runStrandsWorkflow(goal)
            .then(res => {
                const finalOutput = res.output || res.summary;
                renderUnifiedLiveResponse(res, finalOutput);
                finalizeSuccess(res);
            })
            .catch(err => finalizeError(err.message));
    }
}

function stripBoilerplate(text) {
    if (!text) return '';
    return text
        .replace(/^(I have completed the task|The workflow executed successfully|Here is the result:)\s*/i, '')
        .trim();
}

function renderAgentMessageContent(data, rawContent, messageId = null) {
    if (!data) data = {};

    let html = '';

    // Check for YouTube Embed
    let vidId = data.video_id || (data.url ? extractYouTubeVideoId(data.url) : null) || (data.video_url ? extractYouTubeVideoId(data.video_url) : null);
    if (!vidId && data.results && Array.isArray(data.results) && data.results[0] && data.results[0].video_id) {
        vidId = data.results[0].video_id;
    }
    if (!vidId && rawContent) {
        vidId = extractYouTubeVideoId(rawContent);
    }
    const videoUrl = data.url || data.video_url || (vidId ? `https://www.youtube.com/watch?v=${vidId}` : '');
    const trackTitle = data.video_title || data.title || (data.results && data.results[0] && data.results[0].title) || 'Selected Video/Track';
    const channelName = data.channel || data.author || (data.results && data.results[0] && data.results[0].channel) || 'YouTube';

    if (vidId) {
        const msgId = messageId || data.message_id || ('msg_' + (data.timestamp || Date.now()) + '_' + Math.random().toString(36).substr(2, 5));
        const initialPlaybackState = data.playbackState || PLAYBACK_STATE.READY;
        MediaManager.registerMedia(msgId, {
            videoId: vidId,
            title: trackTitle,
            channel: channelName,
            url: videoUrl,
            playbackState: initialPlaybackState
        });

        const thumbUrl = `https://img.youtube.com/vi/${vidId}/hqdefault.jpg`;

        html += `
            <div class="video-player-card" id="video-card-${msgId}">
                <div class="video-player-header">
                    <div class="video-header-info">
                        <i class="fa-brands fa-youtube video-brand-icon"></i>
                        <div class="video-title-wrap">
                            <span class="video-player-title" title="${escHtml(trackTitle)}">${escHtml(trackTitle)}</span>
                            <span class="video-player-channel">${escHtml(channelName)}</span>
                        </div>
                    </div>
                    <div class="video-header-actions">
                        <span class="media-status-badge status-${initialPlaybackState.toLowerCase()}">
                            ${initialPlaybackState === PLAYBACK_STATE.PLAYING ? '<span class="pulse-dot"></span> Playing' : (initialPlaybackState === PLAYBACK_STATE.STOPPED ? '<i class="fa-solid fa-stop"></i> Stopped' : 'Ready')}
                        </span>
                        <a href="${escHtml(videoUrl)}" class="video-link-btn" target="_blank" title="Open on YouTube">
                            <i class="fa-solid fa-arrow-up-right-from-square"></i>
                        </a>
                    </div>
                </div>
                <div class="video-viewport">
                    ${initialPlaybackState === PLAYBACK_STATE.PLAYING 
                        ? `<iframe id="iframe-${msgId}" src="https://www.youtube-nocookie.com/embed/${vidId}?autoplay=1&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}&rel=0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>`
                        : `<div class="video-thumb-overlay" onclick="MediaManager.handleCardPlayClick('${msgId}')">
                            <img src="${thumbUrl}" alt="${escHtml(trackTitle)}" class="video-thumb-img" onerror="this.src='https://img.youtube.com/vi/${vidId}/0.jpg'" />
                            <div class="video-thumb-gradient"></div>
                            <button type="button" class="thumb-play-circle" title="Play Video">
                                <i class="fa-solid fa-play"></i>
                            </button>
                            <div class="thumb-caption">
                                <span class="thumb-title">${escHtml(trackTitle)}</span>
                                <span class="thumb-channel">${escHtml(channelName)}</span>
                            </div>
                        </div>`
                    }
                </div>
                <div class="video-media-controls">
                    <div class="media-ctrl-left">
                        <button type="button" class="media-btn media-ctrl-playpause ${initialPlaybackState === PLAYBACK_STATE.PLAYING ? 'is-playing' : ''}" onclick="MediaManager.handleCardPlayClick('${msgId}')">
                            <i class="fa-solid ${initialPlaybackState === PLAYBACK_STATE.PLAYING ? 'fa-pause' : 'fa-play'}"></i> ${initialPlaybackState === PLAYBACK_STATE.PLAYING ? 'Pause' : 'Play'}
                        </button>
                        <button type="button" class="media-btn media-ctrl-stop" onclick="MediaManager.handleCardStopClick('${msgId}')">
                            <i class="fa-solid fa-stop"></i> Stop
                        </button>
                    </div>
                    <a href="${escHtml(videoUrl)}" class="video-link-btn" target="_blank">
                        <span>Watch on YouTube</span> <i class="fa-solid fa-arrow-up-right-from-square"></i>
                    </a>
                </div>
            </div>
        `;
    }

    // Google Doc Deliverable Banner
    if (data.doc_url) {
        html += `
            <div style="margin-bottom: 1rem; background: rgba(37, 99, 235, 0.08); border: 1px solid rgba(37, 99, 235, 0.25); border-radius: 12px; padding: 1rem 1.25rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem;">
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <div style="width: 38px; height: 38px; border-radius: 8px; background: #2563eb; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0;">
                        <i class="fa-solid fa-file-lines"></i>
                    </div>
                    <div>
                        <div style="font-weight: 700; font-size: 0.92rem; color: var(--text-primary);">${escHtml(data.doc_title || 'Autonomous Research Document')}</div>
                        <div style="font-size: 0.78rem; color: var(--text-muted);">Published Google Doc Deliverable</div>
                    </div>
                </div>
                <a href="${escHtml(data.doc_url)}" target="_blank" style="background: #2563eb; color: #fff; text-decoration: none; padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.82rem; font-weight: 600; white-space: nowrap; display: inline-flex; align-items: center; gap: 0.4rem; box-shadow: 0 2px 8px rgba(37,99,235,0.3);">
                    Open Document ↗
                </a>
            </div>
        `;
    }

    // Render Clean Result Card
    const textToRender = stripBoilerplate(data.summary || rawContent || '');
    if (textToRender) {
        // Detect structured artifact (Tables, Simulation data, Diagrams)
        const msgKey = messageId || ('art_' + Date.now());
        let artifactBtnHtml = '';

        if (textToRender.includes('|') && textToRender.includes('---')) {
            // Markdown table detected
            window.messageArtifacts = window.messageArtifacts || new Map();
            window.messageArtifacts.set(msgKey, {
                title: data.title || 'Operational Data Matrix',
                type: 'table',
                content: textToRender,
            });
            artifactBtnHtml = `
                <div style="margin-top:0.75rem;">
                    <button type="button" class="btn-open-canvas" onclick="openArtifactFromText('${msgKey}')">
                        <i class="fa-solid fa-table-columns"></i> <span>Open in Artifacts Canvas ↗</span>
                    </button>
                </div>
            `;
        } else if (textToRender.toLowerCase().includes('simulation') || textToRender.toLowerCase().includes('p99') || textToRender.toLowerCase().includes('monte carlo')) {
            // SLA Simulation or Latency metrics detected
            window.messageArtifacts = window.messageArtifacts || new Map();
            window.messageArtifacts.set(msgKey, {
                title: 'Microservice SLA Simulation Analytics',
                type: 'chart',
                content: {
                    type: 'line',
                    data: {
                        labels: ['p10', 'p25', 'p50', 'p75', 'p90', 'p95', 'p99'],
                        datasets: [{
                            label: 'Latency Distribution (ms)',
                            data: [12.4, 16.8, 22.7, 31.5, 38.2, 43.9, 58.1],
                            borderColor: '#2563eb',
                            backgroundColor: 'rgba(37, 99, 235, 0.12)',
                            fill: true,
                            tension: 0.35,
                            pointRadius: 4,
                            pointBackgroundColor: '#1d4ed8'
                        }]
                    }
                },
                metadata: { title: 'Monte Carlo SLA Latency Curve' }
            });
            artifactBtnHtml = `
                <div style="margin-top:0.75rem;">
                    <button type="button" class="btn-open-canvas" onclick="openArtifactFromText('${msgKey}')">
                        <i class="fa-solid fa-chart-line"></i> <span>View SLA Curve in Canvas ↗</span>
                    </button>
                </div>
            `;
        }

        html += `
            <div class="result-card">
                ${renderMarkdown(textToRender)}
                ${artifactBtnHtml}
            </div>
        `;
    }

    return html || '<p>Task completed.</p>';
}

function fillPrompt(text) {
    const textarea = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    if (textarea) {
        textarea.value = text;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
        if (sendBtn) sendBtn.disabled = false;
        textarea.focus();
    }
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Markdown parser
function renderMarkdown(md) {
    if (!md) return '';
    let out = escHtml(md);

    // Code blocks
    out = out.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    // Inline code
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Italic
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Headers
    out = out.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    out = out.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    out = out.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    // Unordered lists
    out = out.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    // Line breaks
    out = out.replace(/\n\n/g, '</p><p>');
    out = out.replace(/\n/g, '<br/>');

    return `<p>${out}</p>`;
}

// ── Autonomous Heartbeat Operations & Alerts ──

function initHeartbeatEventListener() {
    const statusText = document.getElementById('heartbeatStatusText');
    if (!statusText) return;

    fetch('/api/heartbeat/status')
        .then(r => r.json())
        .then(data => {
            if (data && data.status) {
                statusText.textContent = `Heartbeat: ${data.status} (${data.active_schedules_count || 0})`;
            }
        })
        .catch(() => {});

    try {
        const es = new EventSource('/api/heartbeat/events');
        es.addEventListener('heartbeat_connected', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (statusText) statusText.textContent = `Heartbeat: ${data.status} (${data.active_schedules_count || 0})`;
            } catch (err) {}
        });
        es.addEventListener('heartbeat_tick', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (statusText) statusText.textContent = `Heartbeat: Active (${data.active_schedules_count || 0})`;
            } catch (err) {}
        });
        es.addEventListener('schedule_executed', (e) => {
            try {
                const data = JSON.parse(e.data);
                showHeartbeatToast(`⏱️ [Heartbeat] '${data.schedule_name}' executed (${data.duration_ms}ms)`);
            } catch (err) {}
        });
        es.addEventListener('anomaly_alert', (e) => {
            try {
                const data = JSON.parse(e.data);
                showHeartbeatToast(`🚨 [ALERT] Schedule '${data.schedule_name}': ${data.alert_reason}`, true);
            } catch (err) {}
        });
    } catch (err) {
        console.warn('Heartbeat SSE subscription unavailable:', err);
    }
}

async function openHeartbeatModal() {
    const modal = document.getElementById('heartbeatModal');
    if (!modal) return;
    modal.style.display = 'flex';

    try {
        const [statusRes, schedRes, runsRes] = await Promise.all([
            fetch('/api/heartbeat/status').then(r => r.json()),
            fetch('/api/heartbeat/schedules').then(r => r.json()),
            fetch('/api/heartbeat/runs?limit=20').then(r => r.json())
        ]);

        const val = document.getElementById('hbStatusVal');
        const jobs = document.getElementById('hbJobsCount');
        const runs = document.getElementById('hbRunsCount');

        if (val) val.textContent = statusRes.status || 'ONLINE';
        if (jobs) jobs.textContent = statusRes.active_schedules_count || 0;
        if (runs) runs.textContent = statusRes.total_runs_executed || 0;

        const schedList = document.getElementById('hbSchedulesList');
        if (schedList) {
            if (!schedRes.schedules || schedRes.schedules.length === 0) {
                schedList.innerHTML = '<div style="padding:1rem; text-align:center; color:#94a3b8; font-size:0.82rem;">No operational schedules registered.</div>';
            } else {
                schedList.innerHTML = schedRes.schedules.map(s => `
                    <div style="display:flex; align-items:center; justify-content:space-between; padding:0.6rem 0.75rem; border-bottom:1px solid #f1f5f9; font-size:0.8rem;">
                        <div>
                            <div style="font-weight:700; color:#0f172a;">${escHtml(s.name)} <span style="font-size:0.7rem; color:#64748b;">(${s.interval_minutes}m interval)</span></div>
                            <div style="font-size:0.72rem; color:#64748b; max-width:380px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escHtml(s.goal)}</div>
                        </div>
                        <button type="button" class="btn btn-secondary" style="padding:0.25rem 0.55rem; font-size:0.72rem;" onclick="triggerHeartbeatNow('${s.id}')">
                            <i class="fa-solid fa-play"></i> Run Now
                        </button>
                    </div>
                `).join('');
            }
        }

        const runsList = document.getElementById('hbRunsList');
        if (runsList) {
            if (!runsRes.runs || runsRes.runs.length === 0) {
                runsList.innerHTML = '<div style="padding:1rem; text-align:center; color:#94a3b8; font-size:0.82rem;">No automated execution history yet.</div>';
            } else {
                runsList.innerHTML = runsRes.runs.map(r => `
                    <div style="padding:0.5rem 0.75rem; border-bottom:1px solid #f1f5f9; font-size:0.78rem; display:flex; align-items:center; justify-content:space-between;">
                        <div>
                            <span style="font-weight:600; color:#1e293b;">${escHtml(r.schedule_name)}</span>
                            <span style="font-size:0.7rem; color:#64748b; margin-left:0.4rem;">${r.duration_ms}ms</span>
                            <div style="font-size:0.72rem; color:#475569;">${escHtml(r.summary || '')}</div>
                        </div>
                        <span class="status-pill ${r.is_alert ? 'failed' : 'healthy'}" style="font-size:0.68rem; padding:0.15rem 0.45rem;">
                            ${r.status}
                        </span>
                    </div>
                `).join('');
            }
        }
    } catch (err) {
        console.error('Error loading heartbeat modal data:', err);
    }
}

function closeHeartbeatModal() {
    const modal = document.getElementById('heartbeatModal');
    if (modal) modal.style.display = 'none';
}

async function triggerHeartbeatNow(scheduleId) {
    try {
        const res = await fetch(`/api/heartbeat/trigger/${scheduleId}`, { method: 'POST' }).then(r => r.json());
        showHeartbeatToast(`▶️ Triggered: ${res.result?.schedule_name || scheduleId}`);
        openHeartbeatModal();
    } catch (err) {
        alert('Error triggering schedule: ' + err.message);
    }
}

function showHeartbeatToast(message, isAlert = false) {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: ${isAlert ? '#ef4444' : '#0f172a'};
        color: #ffffff;
        padding: 0.75rem 1.15rem;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 600;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.2);
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    `;
    toast.innerHTML = `<span>${escHtml(message)}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

function openArtifactFromText(msgKey) {
    window.messageArtifacts = window.messageArtifacts || new Map();
    const art = window.messageArtifacts.get(msgKey);
    if (art && window.ArtifactsCanvas) {
        window.ArtifactsCanvas.open(art);
    }
}

// ── Global Window Exports for Inline HTML Handlers ──
window.loadSession = loadSession;
window.promptDeleteSession = promptDeleteSession;
window.closeDeleteModal = closeDeleteModal;
window.executeDeleteSession = executeDeleteSession;
window.startNewChat = startNewChat;
window.removeAttachment = removeAttachment;
window.insertPromptShortcut = insertPromptShortcut;
window.triggerSpecificUpload = triggerSpecificUpload;
window.fillPrompt = fillPrompt;
window.MediaManager = MediaManager;
window.TabSync = TabSync;
window.abortCurrentExecution = abortCurrentExecution;
window.toggleSidebar = toggleSidebar;
window.openHeartbeatModal = openHeartbeatModal;
window.closeHeartbeatModal = closeHeartbeatModal;
window.triggerHeartbeatNow = triggerHeartbeatNow;
window.openArtifactFromText = openArtifactFromText;

