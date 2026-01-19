/**
 * Admin page functionality
 */

const API_BASE = '/api/v1';

const admin = {
    servers: [],

    /**
     * Initialize admin page
     */
    init() {
        this.setupEventListeners();
        this.loadServers();
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Add server button
        document.getElementById('add-server-btn').addEventListener('click', () => {
            this.openServerModal();
        });

        // Modal close handlers
        document.getElementById('close-server-modal').addEventListener('click', () => {
            this.closeServerModal();
        });
        document.getElementById('server-modal-overlay').addEventListener('click', () => {
            this.closeServerModal();
        });

        // Save server button
        document.getElementById('save-server-btn').addEventListener('click', () => {
            this.saveServer();
        });

        // Close modal on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeServerModal();
            }
        });
    },

    /**
     * Load servers from API
     */
    async loadServers() {
        try {
            const response = await fetch(`${API_BASE}/admin/servers`);
            if (!response.ok) {
                throw new Error('Failed to fetch servers');
            }
            this.servers = await response.json();
            this.renderServers();
        } catch (error) {
            console.error('Failed to load servers:', error);
            this.showError('Failed to load servers');
        }
    },

    /**
     * Render servers list
     */
    renderServers() {
        const container = document.getElementById('servers-list');

        if (this.servers.length === 0) {
            container.innerHTML = `
                <div class="empty-servers">
                    <p>No servers configured yet.</p>
                    <button class="add-btn" onclick="admin.openServerModal()">
                        <span class="icon">+</span>
                        Add your first server
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = this.servers.map(server => `
            <div class="server-item" data-id="${server.id}">
                <div class="server-status ${server.active ? 'active' : 'inactive'}"></div>
                <div class="server-info">
                    <div class="server-name">${this.escapeHtml(server.friendly_name)}</div>
                    <div class="server-url">${this.escapeHtml(server.url)}</div>
                </div>
                <div class="server-actions">
                    <button class="edit-btn" onclick="admin.editServer(${server.id})">Edit</button>
                    <button class="delete-btn" onclick="admin.deleteServer(${server.id})">Delete</button>
                </div>
            </div>
        `).join('');
    },

    /**
     * Open server modal for adding
     */
    openServerModal(server = null) {
        const modal = document.getElementById('server-modal');
        const title = document.getElementById('server-modal-title');
        const idInput = document.getElementById('server-id');
        const nameInput = document.getElementById('server-name');
        const urlInput = document.getElementById('server-url');
        const activeInput = document.getElementById('server-active');

        if (server) {
            title.textContent = 'Edit Server';
            idInput.value = server.id;
            nameInput.value = server.friendly_name;
            urlInput.value = server.url;
            activeInput.checked = server.active;
        } else {
            title.textContent = 'Add Server';
            idInput.value = '';
            nameInput.value = '';
            urlInput.value = '';
            activeInput.checked = true;
        }

        modal.classList.remove('hidden');
        nameInput.focus();
    },

    /**
     * Close server modal
     */
    closeServerModal() {
        document.getElementById('server-modal').classList.add('hidden');
    },

    /**
     * Edit a server
     */
    editServer(id) {
        const server = this.servers.find(s => s.id === id);
        if (server) {
            this.openServerModal(server);
        }
    },

    /**
     * Save server (create or update)
     */
    async saveServer() {
        const idInput = document.getElementById('server-id');
        const nameInput = document.getElementById('server-name');
        const urlInput = document.getElementById('server-url');
        const activeInput = document.getElementById('server-active');

        const name = nameInput.value.trim();
        const url = urlInput.value.trim();
        const active = activeInput.checked;

        if (!name || !url) {
            alert('Please fill in all fields');
            return;
        }

        const data = {
            friendly_name: name,
            url: url,
            active: active
        };

        try {
            let response;
            if (idInput.value) {
                // Update existing server
                response = await fetch(`${API_BASE}/admin/servers/${idInput.value}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            } else {
                // Create new server
                response = await fetch(`${API_BASE}/admin/servers`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            }

            if (!response.ok) {
                throw new Error('Failed to save server');
            }

            this.closeServerModal();
            await this.loadServers();
        } catch (error) {
            console.error('Failed to save server:', error);
            alert('Failed to save server');
        }
    },

    /**
     * Delete a server
     */
    async deleteServer(id) {
        const server = this.servers.find(s => s.id === id);
        if (!server) return;

        if (!confirm(`Delete server "${server.friendly_name}"?`)) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/admin/servers/${id}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Failed to delete server');
            }

            await this.loadServers();
        } catch (error) {
            console.error('Failed to delete server:', error);
            alert('Failed to delete server');
        }
    },

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Show error message
     */
    showError(message) {
        const container = document.getElementById('servers-list');
        container.innerHTML = `
            <div class="empty-servers">
                <p style="color: var(--error);">${this.escapeHtml(message)}</p>
                <button class="add-btn" onclick="admin.loadServers()">Retry</button>
            </div>
        `;
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => admin.init());
