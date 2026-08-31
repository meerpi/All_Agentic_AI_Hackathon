/* ==========================================================================
   TASKMASTER — AUTHENTICATION & SQLITE DATABASE API CLIENT
   Multi-User Session Isolation, Token Auth, Real-Time SSE Streaming
   ========================================================================== */

// ── 1. Authentication Manager ──
const AuthManager = {
    TOKEN_KEY: 'taskmaster_auth_token',
    USER_KEY: 'taskmaster_user',

    getToken() {
        return localStorage.getItem(this.TOKEN_KEY);
    },

    setToken(token) {
        localStorage.setItem(this.TOKEN_KEY, token);
    },

    getUser() {
        try {
            const raw = localStorage.getItem(this.USER_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    },

    setUser(user) {
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    },

    isAuthenticated() {
        return !!this.getToken();
    },

    getAuthHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    },

    async checkSession() {
        const token = this.getToken();
        if (!token) return null;
        try {
            const res = await fetch('/api/auth/me', {
                headers: this.getAuthHeaders()
            });
            const data = await res.json();
            if (res.ok && data.status === 'SUCCESS') {
                this.setUser(data.user);
                return data.user;
            } else {
                this.clear();
                return null;
            }
        } catch (e) {
            return this.getUser();
        }
    },

    async logout() {
        const token = this.getToken();
        if (token) {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: this.getAuthHeaders()
                });
            } catch (e) {}
        }
        this.clear();
        window.location.href = '/auth';
    },

    clear() {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.USER_KEY);
        localStorage.removeItem('taskmaster_active_session_id');
    }
};

// ── 2. Taskmaster Core API Client ──
const TaskmasterAPI = {
    // ── Health & Environment ──
    async getHealth() {
        try {
            const res = await fetch('/api/health');
            return await res.json();
        } catch (e) {
            return { status: 'OFFLINE', error: e.message };
        }
    },

    // ── Tool Listing ──
    async getTools() {
        try {
            const res = await fetch('/api/agent/tools');
            return await res.json();
        } catch (e) {
            return { tools: [] };
        }
    },

    // ── Run Workflow (Synchronous Fallback) ──
    async runWorkflow(goal, context = {}) {
        const res = await fetch('/api/agent/run', {
            method: 'POST',
            headers: AuthManager.getAuthHeaders(),
            body: JSON.stringify({ goal, context })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Execution failed');
        }
        return await res.json();
    },

    // ── Stream Workflow (Real-Time SSE Events) ──
    streamWorkflow(goal, onEvent, onError, onComplete) {
        const token = AuthManager.getToken() || '';
        const url = `/api/agent/stream?goal=${encodeURIComponent(goal)}&token=${encodeURIComponent(token)}`;
        const es = new EventSource(url);
        let hasCompleted = false;

        es.addEventListener('phase_transition', (e) => {
            try { onEvent('phase_transition', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('plan_generated', (e) => {
            try { onEvent('plan_generated', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('step_started', (e) => {
            try { onEvent('step_started', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('step_completed', (e) => {
            try { onEvent('step_completed', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('step_failed', (e) => {
            try { onEvent('step_failed', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('step_correction', (e) => {
            try { onEvent('step_correction', JSON.parse(e.data)); } catch (err) {}
        });

        es.addEventListener('workflow_completed', (e) => {
            try {
                hasCompleted = true;
                const data = JSON.parse(e.data);
                onEvent('workflow_completed', data);
                es.close();
                if (onComplete) onComplete(data);
            } catch (err) {
                es.close();
            }
        });

        es.addEventListener('workflow_error', (e) => {
            try {
                hasCompleted = true;
                const data = JSON.parse(e.data);
                if (onError) onError(new Error(data.error || 'Workflow execution error'));
            } catch (err) {
                if (onError) onError(new Error('Unknown streaming error'));
            }
            es.close();
        });

        es.addEventListener('done', () => {
            hasCompleted = true;
            es.close();
        });

        es.onerror = (err) => {
            es.close();
            if (!hasCompleted && onError) {
                onError(err);
            }
        };

        return es;
    },

    // ── Fetch Traces ──
    async getTraces(workflowId) {
        try {
            const res = await fetch(`/api/agent/traces/${workflowId}`);
            return await res.json();
        } catch (e) {
            return { traces: [] };
        }
    },

    // ── Browser Status ──
    async getBrowserStatus() {
        try {
            const res = await fetch('/api/browser/status');
            return await res.json();
        } catch (e) {
            return { active: false };
        }
    },

    // ── Stop Background Media ──
    async stopMedia() {
        try {
            const res = await fetch('/api/agent/media/stop', { method: 'POST' });
            return await res.json();
        } catch (e) {
            return { status: 'ERROR', error: e.message };
        }
    },

    // ── Browser Screenshot ──
    async getBrowserScreenshot() {
        try {
            const res = await fetch('/api/browser/screenshot?annotated=true');
            return await res.json();
        } catch (e) {
            return null;
        }
    }
};

// ── 3. Persistent SQLite Database Chat Manager (Per-User Storage) ──
const ChatStorage = {
    ACTIVE_KEY: 'taskmaster_active_session_id',
    _cachedSessions: [],

    getActiveSessionId() {
        return localStorage.getItem(this.ACTIVE_KEY);
    },

    setActiveSessionId(id) {
        if (id) {
            localStorage.setItem(this.ACTIVE_KEY, id);
        } else {
            localStorage.removeItem(this.ACTIVE_KEY);
        }
    },

    // Fetch user sessions from SQLite database
    async getSessions() {
        try {
            const res = await fetch('/api/chat/sessions', {
                headers: AuthManager.getAuthHeaders()
            });
            if (res.status === 401) {
                AuthManager.logout();
                return [];
            }
            const data = await res.json();
            if (res.ok && data.status === 'SUCCESS') {
                this._cachedSessions = data.sessions || [];
                return this._cachedSessions;
            }
        } catch (e) {
            console.warn('Could not fetch sessions from SQLite, using cache:', e);
        }
        return this._cachedSessions || [];
    },

    // Fetch session messages from SQLite database
    async getSessionMessages(sessionId) {
        if (!sessionId) return [];
        try {
            const res = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
                headers: AuthManager.getAuthHeaders()
            });
            if (res.status === 401) {
                AuthManager.logout();
                return [];
            }
            const data = await res.json();
            if (res.ok && data.status === 'SUCCESS') {
                const msgs = data.messages || [];
                return msgs.map(m => {
                    if (m.data && m.data.attachments) {
                        m.attachments = m.data.attachments;
                    }
                    return m;
                });
            }
        } catch (e) {
            console.error('Failed to get session messages from SQLite:', e);
        }
        return [];
    },

    // Create session in SQLite database
    async createSession(initialGoal = 'New Chat') {
        const title = initialGoal.length > 36 ? initialGoal.substring(0, 36) + '...' : initialGoal;
        const sessionId = 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        try {
            const res = await fetch('/api/chat/sessions', {
                method: 'POST',
                headers: AuthManager.getAuthHeaders(),
                body: JSON.stringify({ title, session_id: sessionId })
            });
            const data = await res.json();
            if (res.ok && data.status === 'SUCCESS') {
                this.setActiveSessionId(sessionId);
                return data.session;
            }
        } catch (e) {
            console.error('Failed to create session in SQLite:', e);
        }
        this.setActiveSessionId(sessionId);
        return { id: sessionId, title, messages: [] };
    },

    // Add message to SQLite database
    async addMessage(sessionId, message) {
        try {
            const payloadData = message.data || (message.attachments ? { attachments: message.attachments } : null);
            await fetch(`/api/chat/sessions/${sessionId}/messages`, {
                method: 'POST',
                headers: AuthManager.getAuthHeaders(),
                body: JSON.stringify({
                    role: message.role,
                    content: message.content,
                    data: payloadData,
                    timestamp: message.timestamp || Date.now()
                })
            });
        } catch (e) {
            console.error('Failed to save message to SQLite:', e);
        }
    },

    // Rename session in SQLite database
    async renameSession(sessionId, title) {
        try {
            await fetch(`/api/chat/sessions/${sessionId}/rename`, {
                method: 'POST',
                headers: AuthManager.getAuthHeaders(),
                body: JSON.stringify({ title })
            });
        } catch (e) {
            console.error('Failed to rename session in SQLite:', e);
        }
    },

    // Delete session from SQLite database
    async deleteSession(sessionId) {
        try {
            await fetch(`/api/chat/sessions/${sessionId}`, {
                method: 'DELETE',
                headers: AuthManager.getAuthHeaders()
            });
            if (this.getActiveSessionId() === sessionId) {
                const sessions = await this.getSessions();
                const nextId = sessions.length > 0 ? sessions[0].id : null;
                this.setActiveSessionId(nextId);
            }
        } catch (e) {
            console.error('Failed to delete session in SQLite:', e);
        }
    }
};
