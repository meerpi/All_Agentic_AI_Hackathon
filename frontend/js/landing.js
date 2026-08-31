/* ==========================================================================
   TASKMASTER — HERO LANDING PAGE CONTROLLER & LIVE ANIMATIONS
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initAuthNavState();
    startHeroPhraseAnimation();
    startDagAnimationLoop();
});

// Update auth button state
function initAuthNavState() {
    const token = localStorage.getItem('taskmaster_auth_token');
    const navSignInBtn = document.getElementById('navSignInBtn');

    if (token && navSignInBtn) {
        navSignInBtn.innerHTML = '<span>Account</span> <i class="fa-solid fa-user"></i>';
        navSignInBtn.href = '/chat';
    }
}

// Dynamic Realistic Keyboard Typewriter Animation
function startHeroPhraseAnimation() {
    const phrases = [
        "Autonomous Real-World Action",
        "Self-Healing DAG Execution",
        "Intelligent Browser Automation",
        "End-to-End Task Deliverables",
        "Multi-Tool Workflow Execution",
        "Multi-Agent Council Orchestration"
    ];

    let phraseIndex = 0;
    let charIndex = phrases[0].length;
    let isDeleting = false;
    const el = document.getElementById('dynamicHeroPhrase');
    if (!el) return;

    function typeLoop() {
        const currentPhrase = phrases[phraseIndex];

        if (isDeleting) {
            // Deleting backward letter-by-letter
            charIndex--;
            el.textContent = currentPhrase.substring(0, charIndex);

            if (charIndex === 0) {
                isDeleting = false;
                phraseIndex = (phraseIndex + 1) % phrases.length;
                setTimeout(typeLoop, 400); // Pause before typing next phrase
                return;
            }
            setTimeout(typeLoop, 30); // Fast backspacing speed
        } else {
            // Typing forward letter-by-letter
            charIndex++;
            el.textContent = currentPhrase.substring(0, charIndex);

            if (charIndex === currentPhrase.length) {
                isDeleting = true;
                setTimeout(typeLoop, 2200); // Pause to read complete phrase
                return;
            }
            // Realistic keyboard typing cadence
            const typeDelay = Math.floor(Math.random() * 25) + 55;
            setTimeout(typeLoop, typeDelay);
        }
    }

    // Initial pause on pre-rendered sentence before first backspace
    setTimeout(() => {
        isDeleting = true;
        typeLoop();
    }, 2000);
}

// Continuous Live DAG Execution Pipeline Animation
function startDagAnimationLoop() {
    const steps = [
        {
            title: "Goal Received",
            subPending: "Pending intent",
            subActive: "Analyzing intent...",
            subDone: "Intent analyzed",
            timeDone: "00:02"
        },
        {
            title: "Plan DAG",
            subPending: "Pending DAG",
            subActive: "Decomposing tasks...",
            subDone: "2 steps planned",
            timeDone: "00:04"
        },
        {
            title: "Execute Tasks",
            subPending: "Pending tools",
            subActive: "Running tools...",
            subDone: "All tools passed",
            timeDone: "02:18"
        },
        {
            title: "Synthesize Results",
            subPending: "Pending data",
            subActive: "Synthesizing data...",
            subDone: "Data synthesized",
            timeDone: "02:24"
        },
        {
            title: "Deliver Output",
            subPending: "Pending delivery",
            subActive: "Rendering report...",
            subDone: "Delivered 100%",
            timeDone: "02:26"
        }
    ];

    let currentActiveStep = 2; // Start on Step 3 for immediate aesthetic punch

    function updateStepUI(stepIndex) {
        for (let i = 0; i < 5; i++) {
            const card = document.getElementById(`stepCard${i + 1}`);
            const icon = document.getElementById(`stepIcon${i + 1}`);
            const sub = document.getElementById(`stepSub${i + 1}`);
            const time = document.getElementById(`stepTime${i + 1}`);

            if (!card || !icon || !sub || !time) continue;

            card.className = 'dag-step-card';

            if (i < stepIndex) {
                // Completed Step
                card.classList.add('completed');
                icon.className = 'fa-regular fa-circle-check step-icon-success';
                sub.className = 'step-subtitle';
                sub.textContent = steps[i].subDone;
                time.textContent = steps[i].timeDone;
            } else if (i === stepIndex) {
                // Active Running Step
                card.classList.add('active-running');
                icon.className = 'fa-solid fa-spinner fa-spin step-icon-running';
                sub.className = 'step-subtitle text-running';
                sub.textContent = steps[i].subActive;
                time.textContent = '00:0' + Math.floor(Math.random() * 5 + 1);
            } else {
                // Pending Step
                card.classList.add('pending');
                if (i === 3) icon.className = 'fa-solid fa-circle-nodes step-icon-pending';
                else if (i === 4) icon.className = 'fa-regular fa-clock step-icon-pending';
                else icon.className = 'fa-regular fa-circle step-icon-pending';
                sub.className = 'step-subtitle';
                sub.textContent = steps[i].subPending;
                time.textContent = '--:--';
            }
        }
    }

    // Initialize initial state
    updateStepUI(currentActiveStep);

    // Continuous cycling loop
    setInterval(() => {
        currentActiveStep = (currentActiveStep + 1) % 6;
        if (currentActiveStep === 5) {
            // All completed state
            for (let i = 0; i < 5; i++) {
                const card = document.getElementById(`stepCard${i + 1}`);
                const icon = document.getElementById(`stepIcon${i + 1}`);
                const sub = document.getElementById(`stepSub${i + 1}`);
                const time = document.getElementById(`stepTime${i + 1}`);
                if (card && icon && sub && time) {
                    card.className = 'dag-step-card completed';
                    icon.className = 'fa-regular fa-circle-check step-icon-success';
                    sub.className = 'step-subtitle';
                    sub.textContent = steps[i].subDone;
                    time.textContent = steps[i].timeDone;
                }
            }
        } else {
            updateStepUI(currentActiveStep);
        }
    }, 2400);
}

// Interactive Policy & Info Modals
function openPolicyModal(type) {
    const backdrop = document.getElementById('policyModalBackdrop');
    const titleEl = document.getElementById('policyModalTitle');
    const bodyEl = document.getElementById('policyModalBody');
    if (!backdrop || !titleEl || !bodyEl) return;

    const modalData = {
        privacy: {
            title: "Privacy & Data Protection Policy",
            content: `
                <h4>1. Zero Data Scraping & Complete Confidentiality</h4>
                <p>Taskmaster operates with strict privacy guardrails. User prompts, goal executions, and generated artifacts are stored securely in your isolated local SQLite database.</p>
                <h4>2. Client-Side Authentication</h4>
                <p>All authentication tokens are stored locally on your device and validated over cryptographically hashed PBKDF2-SHA256 credentials.</p>
                <h4>3. Tool Authorization</h4>
                <p>Third-party tool connectors (e.g., Google Workspace, Jira Cloud) operate on least-privilege scoping and only execute actions explicitly commanded by the user.</p>
            `
        },
        terms: {
            title: "Terms of Service",
            content: `
                <h4>1. Autonomous Execution & Verification</h4>
                <p>Taskmaster provides multi-agent and DAG task decomposition. Outputs are synthesized using LLM reasoning and must be verified for mission-critical operations.</p>
                <h4>2. Permissible Usage</h4>
                <p>Users agree not to utilize Taskmaster for automated vulnerability exploitation, unauthorized scraping of restricted targets, or destructive web automation.</p>
                <h4>3. Tool Rate Limits</h4>
                <p>Execution quotas adhere to underlying provider limits (Google Gemini API, YouTube Data API, Jira REST API).</p>
            `
        },
        security: {
            title: "Security & Guardrails Overview",
            content: `
                <h4>1. Enterprise Safety Rails</h4>
                <p>Every prompt passes through an automated security filter that checks for prompt injections, system override attempts, and sensitive credential leakage.</p>
                <h4>2. Sandboxed Python & Browser Execution</h4>
                <p>Playwright browser sessions and code executions operate within isolated runtime boundaries with auto-cleanup on task completion.</p>
                <h4>3. Emergency Panic Stop Switch</h4>
                <p>A global media & task termination switch is accessible from both the UI and API at any time to instantly halt background audio, videos, or ongoing tasks.</p>
            `
        },
        integrations: {
            title: "16 Native Tool Connectors",
            content: `
                <h4>Built-in Connectors Suite</h4>
                <p>Taskmaster includes deterministic tooling for:</p>
                <ul>
                    <li><strong>Google Workspace:</strong> Gmail, Docs, Sheets, Calendar, Drive</li>
                    <li><strong>Atlassian Jira:</strong> Issue creation, sprint tracking, board transitions</li>
                    <li><strong>Media & Web:</strong> Playwright Headed/Headless, YouTube Search & Play, Spotify API</li>
                    <li><strong>Developer Sandbox:</strong> Python execution, Terminal command runner, File System CRUD</li>
                </ul>
            `
        },
        browser: {
            title: "Playwright Automation Engine",
            content: `
                <h4>Deep Web Interaction</h4>
                <p>Taskmaster drives full Chromium sessions with intelligent ARIA role detection, human-like mouse trajectories, automatic cookie consent dismissal, and live viewport streaming.</p>
            `
        },
        sqlite: {
            title: "SQLite Multi-User Isolation",
            content: `
                <h4>ACID-Compliant Relational Database</h4>
                <p>Taskmaster utilizes a high-performance SQLite engine with Write-Ahead Logging (WAL mode), salted PBKDF2 password hashing, and strict user-segregated chat session tables.</p>
            `
        }
    };

    const info = modalData[type] || modalData.privacy;
    titleEl.textContent = info.title;
    bodyEl.innerHTML = info.content;
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closePolicyModal() {
    const backdrop = document.getElementById('policyModalBackdrop');
    if (backdrop) {
        backdrop.classList.remove('open');
        document.body.style.overflow = '';
    }
}

