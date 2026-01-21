/**
 * Admin page functionality
 */

const API_BASE = '/api/v1';

const admin = {
    servers: [],
    collections: [],
    adminSettings: {},

    /**
     * Initialize admin page
     */
    init() {
        this.setupEventListeners();
        this.loadServers();
        this.loadCollections();
        this.loadAdminSettings();
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
                this.closeCollectionModal();
            }
        });

        // Collection event listeners
        document.getElementById('add-collection-btn').addEventListener('click', () => {
            this.openCollectionModal();
        });

        document.getElementById('close-collection-modal').addEventListener('click', () => {
            this.closeCollectionModal();
        });
        document.getElementById('collection-modal-overlay').addEventListener('click', () => {
            this.closeCollectionModal();
        });

        document.getElementById('save-collection-btn').addEventListener('click', () => {
            this.saveCollection();
        });

        // Document AI dropdown changes
        document.getElementById('document-ai-query-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('document_ai_query_server_id', e.target.value);
        });
        document.getElementById('document-ai-extraction-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('document_ai_extraction_server_id', e.target.value);
        });
        document.getElementById('document-ai-understanding-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('document_ai_understanding_server_id', e.target.value);
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
            this.populateDocumentAiDropdowns();
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
    },

    // Collection management methods

    /**
     * Load collections from API
     */
    async loadCollections() {
        try {
            const response = await fetch(`${API_BASE}/documents/collections`);
            if (!response.ok) {
                throw new Error('Failed to fetch collections');
            }
            this.collections = await response.json();
            this.renderCollections();
        } catch (error) {
            console.error('Failed to load collections:', error);
            this.showCollectionError('Failed to load collections');
        }
    },

    /**
     * Render collections list
     */
    renderCollections() {
        const container = document.getElementById('collections-list');

        if (this.collections.length === 0) {
            container.innerHTML = `
                <div class="empty-servers">
                    <p>No collections configured yet.</p>
                    <button class="add-btn" onclick="admin.openCollectionModal()">
                        <span class="icon">+</span>
                        Add your first collection
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = this.collections.map(collection => `
            <div class="server-item" data-id="${collection.id}">
                <div class="server-status ${collection.is_default ? 'active' : ''}"></div>
                <div class="server-info">
                    <div class="server-name">
                        ${this.escapeHtml(collection.name)}
                        ${collection.is_default ? '<span class="badge">Default</span>' : ''}
                    </div>
                    <div class="server-url">
                        ${collection.document_count} documents
                        ${collection.description ? ' - ' + this.escapeHtml(collection.description) : ''}
                    </div>
                </div>
                <div class="server-actions">
                    <button class="edit-btn" onclick="admin.editCollection(${collection.id})">Edit</button>
                    ${collection.is_default ? '' : `<button class="delete-btn" onclick="admin.deleteCollection(${collection.id})">Delete</button>`}
                </div>
            </div>
        `).join('');
    },

    /**
     * Open collection modal for adding
     */
    openCollectionModal(collection = null) {
        const modal = document.getElementById('collection-modal');
        const title = document.getElementById('collection-modal-title');
        const idInput = document.getElementById('collection-id');
        const nameInput = document.getElementById('collection-name');
        const descInput = document.getElementById('collection-description');

        if (collection) {
            title.textContent = 'Edit Collection';
            idInput.value = collection.id;
            nameInput.value = collection.name;
            descInput.value = collection.description || '';
        } else {
            title.textContent = 'Add Collection';
            idInput.value = '';
            nameInput.value = '';
            descInput.value = '';
        }

        modal.classList.remove('hidden');
        nameInput.focus();
    },

    /**
     * Close collection modal
     */
    closeCollectionModal() {
        document.getElementById('collection-modal').classList.add('hidden');
    },

    /**
     * Edit a collection
     */
    editCollection(id) {
        const collection = this.collections.find(c => c.id === id);
        if (collection) {
            this.openCollectionModal(collection);
        }
    },

    /**
     * Save collection (create or update)
     */
    async saveCollection() {
        const idInput = document.getElementById('collection-id');
        const nameInput = document.getElementById('collection-name');
        const descInput = document.getElementById('collection-description');

        const name = nameInput.value.trim();
        const description = descInput.value.trim();

        if (!name) {
            alert('Please enter a collection name');
            return;
        }

        const data = { name, description };

        try {
            let response;
            if (idInput.value) {
                // Update existing collection
                response = await fetch(`${API_BASE}/documents/collections/${idInput.value}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            } else {
                // Create new collection
                response = await fetch(`${API_BASE}/documents/collections`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            }

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to save collection');
            }

            this.closeCollectionModal();
            await this.loadCollections();
        } catch (error) {
            console.error('Failed to save collection:', error);
            alert(error.message || 'Failed to save collection');
        }
    },

    /**
     * Delete a collection
     */
    async deleteCollection(id) {
        const collection = this.collections.find(c => c.id === id);
        if (!collection) return;

        if (collection.document_count > 0) {
            if (!confirm(`Delete collection "${collection.name}" and all ${collection.document_count} documents?`)) {
                return;
            }
        } else {
            if (!confirm(`Delete collection "${collection.name}"?`)) {
                return;
            }
        }

        try {
            const response = await fetch(`${API_BASE}/documents/collections/${id}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to delete collection');
            }

            await this.loadCollections();
        } catch (error) {
            console.error('Failed to delete collection:', error);
            alert(error.message || 'Failed to delete collection');
        }
    },

    /**
     * Show collection error message
     */
    showCollectionError(message) {
        const container = document.getElementById('collections-list');
        container.innerHTML = `
            <div class="empty-servers">
                <p style="color: var(--error);">${this.escapeHtml(message)}</p>
                <button class="add-btn" onclick="admin.loadCollections()">Retry</button>
            </div>
        `;
    },

    // Admin settings methods

    /**
     * Load admin settings from API
     */
    async loadAdminSettings() {
        try {
            const response = await fetch(`${API_BASE}/admin/settings`);
            if (!response.ok) {
                throw new Error('Failed to fetch admin settings');
            }
            this.adminSettings = await response.json();
            this.populateDocumentAiDropdowns();
        } catch (error) {
            console.error('Failed to load admin settings:', error);
        }
    },

    /**
     * Populate Document AI dropdowns with servers
     */
    populateDocumentAiDropdowns() {
        const dropdowns = [
            { id: 'document-ai-query-server', setting: 'document_ai_query_server_id' },
            { id: 'document-ai-extraction-server', setting: 'document_ai_extraction_server_id' },
            { id: 'document-ai-understanding-server', setting: 'document_ai_understanding_server_id' }
        ];

        for (const dropdown of dropdowns) {
            const select = document.getElementById(dropdown.id);
            select.innerHTML = '<option value="">-- Select a server --</option>';

            for (const server of this.servers) {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.friendly_name;
                if (this.adminSettings[dropdown.setting] === server.id) {
                    option.selected = true;
                }
                select.appendChild(option);
            }
        }
    },

    /**
     * Save Document AI server setting
     */
    async saveDocumentAiSetting(settingKey, serverId) {
        try {
            const response = await fetch(`${API_BASE}/admin/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    [settingKey]: serverId ? parseInt(serverId) : null
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save setting');
            }

            this.adminSettings = await response.json();
        } catch (error) {
            console.error('Failed to save Document AI setting:', error);
            alert('Failed to save setting');
            // Revert dropdown to previous value
            this.populateDocumentAiDropdowns();
        }
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => admin.init());
