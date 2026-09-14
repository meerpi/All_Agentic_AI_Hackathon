/**
 * TASKMASTER PRO — SPLIT-PANE INTERACTIVE ARTIFACTS CANVAS
 * Claude Artifacts & Cursor Composer Style Engine
 * Handles dynamic tables, Chart.js graphs, Mermaid diagrams, and code previews.
 */

const ArtifactsCanvas = {
    isOpen: false,
    isMaximized: false,
    activeTab: 'visual',
    currentArtifact: null,
    chartInstance: null,

    init() {
        this.pane = document.getElementById('chatArtifactsPane');
        this.titleEl = document.getElementById('artifactCanvasTitle');
        this.badgeEl = document.getElementById('artifactCanvasBadge');
        this.visualViewEl = document.getElementById('artifactVisualView');
        this.rawViewEl = document.getElementById('artifactRawView');
        this.codeContentEl = document.getElementById('artifactCodeContent');

        // Initialize Mermaid if available
        if (window.mermaid) {
            window.mermaid.initialize({
                startOnLoad: false,
                theme: 'neutral',
                securityLevel: 'loose',
                flowchart: { curve: 'basis', htmlLabels: true }
            });
        }
    },

    open(artifact) {
        if (!this.pane) this.init();
        this.currentArtifact = artifact;
        this.isOpen = true;

        if (this.pane) {
            this.pane.classList.add('open');
        }

        // Smart layout: auto-collapse sidebar if screen is under 1400px to give chat & canvas optimal width
        if (window.innerWidth < 1400) {
            const sidebar = document.getElementById('chatSidebar');
            if (sidebar && !sidebar.classList.contains('collapsed')) {
                sidebar.classList.add('collapsed');
                this._sidebarAutoCollapsed = true;
            }
        }

        // Set title and type badge
        const title = artifact.title || 'Deliverable Artifact';
        const type = (artifact.type || 'table').toLowerCase();

        if (this.titleEl) this.titleEl.textContent = title;
        if (this.badgeEl) {
            this.badgeEl.className = `artifacts-type-badge ${type}`;
            const iconMap = {
                table: '<i class="fa-solid fa-table"></i> Table',
                chart: '<i class="fa-solid fa-chart-line"></i> Chart',
                graph: '<i class="fa-solid fa-sitemap"></i> Graph',
                mermaid: '<i class="fa-solid fa-sitemap"></i> Diagram',
                code: '<i class="fa-solid fa-code"></i> Code',
                document: '<i class="fa-solid fa-file-lines"></i> Doc'
            };
            this.badgeEl.innerHTML = iconMap[type] || `<i class="fa-solid fa-cube"></i> ${type.toUpperCase()}`;
        }

        // Render content
        this.switchTab('visual');
        this.renderCurrentArtifact();
    },

    close() {
        this.isOpen = false;
        if (this.pane) {
            this.pane.classList.remove('open', 'maximized');
        }
        this.isMaximized = false;
        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }

        // Restore sidebar if it was auto-collapsed
        if (this._sidebarAutoCollapsed) {
            const sidebar = document.getElementById('chatSidebar');
            if (sidebar) sidebar.classList.remove('collapsed');
            this._sidebarAutoCollapsed = false;
        }
    },

    toggleMaximize() {
        this.isMaximized = !this.isMaximized;
        if (this.pane) {
            this.pane.classList.toggle('maximized', this.isMaximized);
        }
        const btn = document.getElementById('artifactMaximizeBtn');
        if (btn) {
            btn.innerHTML = this.isMaximized 
                ? '<i class="fa-solid fa-compress"></i>' 
                : '<i class="fa-solid fa-expand"></i>';
        }
        // Resize chart if active
        if (this.chartInstance) {
            setTimeout(() => this.chartInstance.resize(), 320);
        }
    },

    switchTab(tab) {
        this.activeTab = tab;
        const visualBtn = document.getElementById('tabVisualBtn');
        const codeBtn = document.getElementById('tabCodeBtn');

        if (visualBtn) visualBtn.classList.toggle('active', tab === 'visual');
        if (codeBtn) codeBtn.classList.toggle('active', tab === 'code');

        if (this.visualViewEl) this.visualViewEl.style.display = tab === 'visual' ? 'block' : 'none';
        if (this.rawViewEl) this.rawViewEl.style.display = tab === 'code' ? 'block' : 'none';

        if (tab === 'code') {
            this.renderRawView();
        }
    },

    renderCurrentArtifact() {
        if (!this.currentArtifact || !this.visualViewEl) return;
        const { type, content, metadata } = this.currentArtifact;

        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }

        this.visualViewEl.innerHTML = '';

        switch (type.toLowerCase()) {
            case 'table':
            case 'sheets':
            case 'matrix':
                this.renderTable(content, metadata);
                break;
            case 'chart':
                this.renderChart(content, metadata);
                break;
            case 'mermaid':
            case 'graph':
                this.renderMermaid(content);
                break;
            default:
                this.renderGenericDocument(content);
                break;
        }
    },

    renderTable(data, metadata = {}) {
        let headers = [];
        let rows = [];

        // Parse 2D array, array of objects, or markdown table
        if (Array.isArray(data)) {
            if (data.length > 0 && Array.isArray(data[0])) {
                headers = data[0];
                rows = data.slice(1);
            } else if (data.length > 0 && typeof data[0] === 'object') {
                headers = Object.keys(data[0]);
                rows = data.map(obj => headers.map(h => obj[h]));
            }
        } else if (typeof data === 'string') {
            // Parse markdown table string
            const lines = data.trim().split('\n').filter(l => l.includes('|'));
            if (lines.length >= 2) {
                headers = lines[0].split('|').map(s => s.trim()).filter(Boolean);
                const dataLines = lines.slice(1).filter(l => !l.replace(/[-|:\s]/g, '') == '');
                rows = dataLines.map(l => l.split('|').map(s => s.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1));
            }
        }

        const totalRows = rows.length;
        const container = document.createElement('div');
        container.className = 'canvas-table-container';

        container.innerHTML = `
            <div class="canvas-table-toolbar">
                <input type="text" class="canvas-table-search" id="canvasTableSearch" placeholder="Search rows..." />
                <div class="canvas-table-meta">
                    <span id="canvasRowCount">${totalRows} rows</span> | 
                    <span>${headers.length} columns</span>
                </div>
            </div>
            <div class="canvas-table-wrapper">
                <table class="canvas-data-table" id="canvasDataTable">
                    <thead>
                        <tr>
                            <th class="row-num">#</th>
                            ${headers.map((h, i) => `<th data-col="${i}">${esc(h)} <i class="fa-solid fa-sort" style="font-size:0.7rem; opacity:0.6;"></i></th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((row, idx) => `
                            <tr>
                                <td class="row-num">${idx + 1}</td>
                                ${row.map(cell => `<td>${esc(String(cell !== undefined ? cell : ''))}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        this.visualViewEl.appendChild(container);

        // Wire real-time search filtering
        const searchInput = container.querySelector('#canvasTableSearch');
        const tbody = container.querySelector('tbody');
        const countSpan = container.querySelector('#canvasRowCount');

        if (searchInput && tbody) {
            searchInput.addEventListener('input', (e) => {
                const term = e.target.value.toLowerCase().trim();
                let visible = 0;
                Array.from(tbody.querySelectorAll('tr')).forEach(tr => {
                    const text = tr.innerText.toLowerCase();
                    const match = !term || text.includes(term);
                    tr.style.display = match ? '' : 'none';
                    if (match) visible++;
                });
                if (countSpan) countSpan.textContent = `${visible} of ${totalRows} rows`;
            });
        }

        // Wire column sorting
        const ths = container.querySelectorAll('th[data-col]');
        ths.forEach(th => {
            let asc = true;
            th.addEventListener('click', () => {
                const colIdx = parseInt(th.getAttribute('data-col'), 10) + 1; // +1 for row-num
                const trs = Array.from(tbody.querySelectorAll('tr'));
                trs.sort((a, b) => {
                    const v1 = a.children[colIdx]?.innerText || '';
                    const v2 = b.children[colIdx]?.innerText || '';
                    const n1 = parseFloat(v1);
                    const n2 = parseFloat(v2);
                    if (!isNaN(n1) && !isNaN(n2)) {
                        return asc ? n1 - n2 : n2 - n1;
                    }
                    return asc ? v1.localeCompare(v2) : v2.localeCompare(v1);
                });
                asc = !asc;
                trs.forEach(tr => tbody.appendChild(tr));
            });
        });
    },

    renderChart(config, metadata = {}) {
        const wrapper = document.createElement('div');
        wrapper.className = 'canvas-chart-wrapper';

        wrapper.innerHTML = `
            <div class="canvas-chart-header">
                <span class="canvas-chart-title">${esc(metadata.title || 'Interactive Analytics Chart')}</span>
                <span style="font-size:0.75rem; color:#64748b;">Generated via Chart.js</span>
            </div>
            <div class="canvas-chart-canvas-box">
                <canvas id="canvasChartElement"></canvas>
            </div>
        `;

        this.visualViewEl.appendChild(wrapper);

        const canvasEl = wrapper.querySelector('#canvasChartElement');
        if (!canvasEl || !window.Chart) return;

        // Default clean professional theme if config is raw data
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { font: { family: 'Outfit', size: 12 } } },
                tooltip: { backgroundColor: '#1e293b', titleFont: { family: 'Outfit', weight: 'bold' } }
            },
            scales: {
                x: { grid: { color: 'rgba(226, 232, 240, 0.6)' }, ticks: { font: { family: 'Outfit', size: 11 } } },
                y: { grid: { color: 'rgba(226, 232, 240, 0.6)' }, ticks: { font: { family: 'Outfit', size: 11 } } }
            }
        };

        const finalConfig = {
            type: config.type || 'line',
            data: config.data || { labels: [], datasets: [] },
            options: { ...defaultOptions, ...(config.options || {}) }
        };

        this.chartInstance = new window.Chart(canvasEl, finalConfig);
    },

    async renderMermaid(code) {
        const container = document.createElement('div');
        container.className = 'canvas-mermaid-container';
        container.id = 'canvasMermaidHost';
        this.visualViewEl.appendChild(container);

        if (window.mermaid) {
            try {
                const id = `mermaid-${Date.now()}`;
                const { svg } = await window.mermaid.render(id, code);
                container.innerHTML = svg;
            } catch (e) {
                container.innerHTML = `<div style="color:#ef4444; font-size:0.85rem;">Failed to render Mermaid diagram: ${esc(e.message)}</div><pre style="margin-top:0.75rem; font-size:0.8rem;">${esc(code)}</pre>`;
            }
        } else {
            container.innerHTML = `<pre>${esc(code)}</pre>`;
        }
    },

    renderGenericDocument(content) {
        const container = document.createElement('div');
        container.style.lineHeight = '1.6';
        container.style.fontSize = '0.9rem';
        container.style.color = '#1e293b';
        container.innerHTML = typeof content === 'string' ? content : `<pre>${esc(JSON.stringify(content, null, 2))}</pre>`;
        this.visualViewEl.appendChild(container);
    },

    renderRawView() {
        if (!this.codeContentEl || !this.currentArtifact) return;
        const { content } = this.currentArtifact;
        const rawText = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
        this.codeContentEl.textContent = rawText;
    },

    exportCSV() {
        if (!this.currentArtifact) return;
        const { content, title } = this.currentArtifact;
        let csv = '';

        if (Array.isArray(content) && content.length > 0) {
            csv = content.map(row => (Array.isArray(row) ? row : Object.values(row)).map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
        } else {
            csv = String(content);
        }

        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(title || 'artifact').replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    },

    copyContent() {
        if (!this.currentArtifact) return;
        const { content } = this.currentArtifact;
        const text = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
        navigator.clipboard.writeText(text).then(() => {
            const btn = document.getElementById('artifactCopyBtn');
            if (btn) {
                const orig = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check" style="color:#10b981;"></i>';
                setTimeout(() => btn.innerHTML = orig, 1800);
            }
        });
    }
};

function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

window.ArtifactsCanvas = ArtifactsCanvas;
document.addEventListener('DOMContentLoaded', () => ArtifactsCanvas.init());
