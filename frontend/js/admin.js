/**
 * Admin page functionality
 */

const API_BASE = '/api/v1';

const admin = {
    servers: [],
    collections: [],
    adminSettings: {},
    availableModels: [],
    serverStatuses: {},
    statusPollingInterval: null,

    /**
     * Initialize admin page
     */
    init() {
        this.setupEventListeners();
        this.loadModels();
        this.loadServers();
        this.loadCollections();
        this.loadAdminSettings();
        this.startStatusPolling();
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

        // Skip contextual retrieval checkbox
        document.getElementById('skip-contextual-retrieval').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('skip_contextual_retrieval', e.target.checked);
        });
    },

    /**
     * Load available models from API
     */
    async loadModels() {
        try {
            const response = await fetch(`${API_BASE}/admin/models`);
            if (!response.ok) {
                throw new Error('Failed to fetch models');
            }
            const data = await response.json();
            this.availableModels = data.models || [];
            this.populateModelDropdown();
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    },

    /**
     * Populate model dropdown with available models
     */
    populateModelDropdown() {
        const select = document.getElementById('server-model-path');
        const currentValue = select.value;

        // Keep the empty option
        select.innerHTML = '<option value="">-- Select a model --</option>';

        for (const model of this.availableModels) {
            const option = document.createElement('option');
            option.value = model.path;
            const sizeMB = (model.size_bytes / (1024 * 1024 * 1024)).toFixed(1);
            option.textContent = `${model.filename} (${sizeMB} GB)`;
            select.appendChild(option);
        }

        // Restore selection if it exists
        if (currentValue) {
            select.value = currentValue;
        }
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
            await this.loadServerStatuses();
            this.renderServers();
            this.populateDocumentAiDropdowns();
        } catch (error) {
            console.error('Failed to load servers:', error);
            this.showError('Failed to load servers');
        }
    },

    /**
     * Extract filename from a full path
     */
    extractFilename(path) {
        if (!path) return null;
        const parts = path.split('/');
        return parts[parts.length - 1];
    },

    /**
     * Load status for all servers
     */
    async loadServerStatuses() {
        const promises = this.servers.map(async (server) => {
            try {
                const response = await fetch(`${API_BASE}/admin/servers/${server.id}/status`);
                if (response.ok) {
                    const data = await response.json();
                    this.serverStatuses[server.id] = data.process_running;
                }
            } catch (error) {
                console.error(`Failed to load status for server ${server.id}:`, error);
                this.serverStatuses[server.id] = false;
            }
        });
        await Promise.all(promises);
    },

    /**
     * Start polling for server statuses
     */
    startStatusPolling() {
        // Poll every 5 seconds
        this.statusPollingInterval = setInterval(async () => {
            if (this.servers.length > 0) {
                await this.loadServerStatuses();
                this.renderServers();
            }
        }, 5000);
    },

    /**
     * Stop status polling
     */
    stopStatusPolling() {
        if (this.statusPollingInterval) {
            clearInterval(this.statusPollingInterval);
            this.statusPollingInterval = null;
        }
    },

    /**
     * Start a server process
     */
    async startServer(id) {
        try {
            const response = await fetch(`${API_BASE}/admin/servers/${id}/start`, {
                method: 'POST'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to start server');
            }

            this.serverStatuses[id] = true;
            this.renderServers();
        } catch (error) {
            console.error('Failed to start server:', error);
            alert(error.message || 'Failed to start server');
        }
    },

    /**
     * Stop a server process
     */
    async stopServer(id) {
        try {
            const response = await fetch(`${API_BASE}/admin/servers/${id}/stop`, {
                method: 'POST'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to stop server');
            }

            this.serverStatuses[id] = false;
            this.renderServers();
        } catch (error) {
            console.error('Failed to stop server:', error);
            alert(error.message || 'Failed to stop server');
        }
    },

    /**
     * Restart a server process
     */
    async restartServer(id) {
        try {
            const response = await fetch(`${API_BASE}/admin/servers/${id}/restart`, {
                method: 'POST'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to restart server');
            }

            this.serverStatuses[id] = true;
            this.renderServers();
        } catch (error) {
            console.error('Failed to restart server:', error);
            alert(error.message || 'Failed to restart server');
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

        container.innerHTML = this.servers.map(server => {
            const modelName = this.extractFilename(server.model_path);
            const modelDisplay = modelName
                ? `<div class="server-model">${this.escapeHtml(modelName)}</div>`
                : '';

            const isRunning = this.serverStatuses[server.id] || false;
            const hasModel = !!server.model_path;

            // Process status indicator: green=running, amber=stopped (has model), gray=inactive (no model)
            let processStatusClass = 'inactive';
            let processStatusText = 'No model';
            if (hasModel) {
                if (isRunning) {
                    processStatusClass = 'running';
                    processStatusText = 'Running';
                } else {
                    processStatusClass = 'stopped';
                    processStatusText = 'Stopped';
                }
            }

            // Process control buttons
            let processControls = '';
            if (hasModel) {
                if (isRunning) {
                    processControls = `
                        <button class="stop-btn" onclick="admin.stopServer(${server.id})">Stop</button>
                        <button class="restart-btn" onclick="admin.restartServer(${server.id})">Restart</button>
                    `;
                } else {
                    processControls = `
                        <button class="start-btn" onclick="admin.startServer(${server.id})">Start</button>
                    `;
                }
            }

            return `
            <div class="server-item" data-id="${server.id}">
                <div class="server-status-indicator ${processStatusClass}" title="${processStatusText}"></div>
                <div class="server-info">
                    <div class="server-name">${this.escapeHtml(server.friendly_name)}</div>
                    <div class="server-url">${this.escapeHtml(server.url)}</div>
                    ${modelDisplay}
                    <div class="server-process-status ${processStatusClass}">${processStatusText}</div>
                </div>
                <div class="server-actions">
                    <div class="process-controls">
                        ${processControls}
                    </div>
                    <button class="edit-btn" onclick="admin.editServer(${server.id})">Edit</button>
                    <button class="delete-btn" onclick="admin.deleteServer(${server.id})">Delete</button>
                </div>
            </div>
        `}).join('');
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
        const modelPathSelect = document.getElementById('server-model-path');
        const parallelInput = document.getElementById('server-parallel');
        const ctxSizeInput = document.getElementById('server-ctx-size');
        const activeInput = document.getElementById('server-active');

        // Refresh model dropdown
        this.populateModelDropdown();

        if (server) {
            title.textContent = 'Edit Server';
            idInput.value = server.id;
            nameInput.value = server.friendly_name;
            urlInput.value = server.url;
            modelPathSelect.value = server.model_path || '';
            parallelInput.value = server.parallel || 1;
            ctxSizeInput.value = server.ctx_size || 32768;
            activeInput.checked = server.active;
        } else {
            title.textContent = 'Add Server';
            idInput.value = '';
            nameInput.value = '';
            urlInput.value = '';
            modelPathSelect.value = '';
            parallelInput.value = '1';
            ctxSizeInput.value = '32768';
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
        const modelPathInput = document.getElementById('server-model-path');
        const parallelInput = document.getElementById('server-parallel');
        const ctxSizeInput = document.getElementById('server-ctx-size');
        const activeInput = document.getElementById('server-active');

        const name = nameInput.value.trim();
        const url = urlInput.value.trim();
        const modelPath = modelPathInput.value.trim() || null;
        const parallel = parseInt(parallelInput.value, 10);
        const ctxSize = parseInt(ctxSizeInput.value, 10);
        const active = activeInput.checked;

        if (!name || !url) {
            alert('Please fill in all required fields');
            return;
        }

        const data = {
            friendly_name: name,
            url: url,
            model_path: modelPath,
            parallel: parallel,
            ctx_size: ctxSize,
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
     * Populate Document AI dropdowns with active servers only
     */
    populateDocumentAiDropdowns() {
        const dropdowns = [
            { id: 'document-ai-query-server', setting: 'document_ai_query_server_id' },
            { id: 'document-ai-extraction-server', setting: 'document_ai_extraction_server_id' },
            { id: 'document-ai-understanding-server', setting: 'document_ai_understanding_server_id' }
        ];

        // Only show active servers in Document AI dropdowns
        const activeServers = this.servers.filter(s => s.active);

        for (const dropdown of dropdowns) {
            const select = document.getElementById(dropdown.id);
            select.innerHTML = '<option value="">-- Select a server --</option>';

            const currentSetting = this.adminSettings[dropdown.setting];

            for (const server of activeServers) {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.friendly_name;
                // Compare as integers to handle any type mismatches
                if (currentSetting != null && parseInt(currentSetting) === parseInt(server.id)) {
                    option.selected = true;
                }
                select.appendChild(option);
            }
        }

        // Set skip contextual retrieval checkbox
        const skipCheckbox = document.getElementById('skip-contextual-retrieval');
        if (skipCheckbox) {
            skipCheckbox.checked = !!this.adminSettings.skip_contextual_retrieval;
        }
    },

    /**
     * Save Document AI server setting
     */
    async saveDocumentAiSetting(settingKey, value) {
        try {
            // Server IDs are strings from dropdowns — parse to int or null
            // Booleans (e.g. skip_contextual_retrieval) pass through as-is
            const parsed = typeof value === 'boolean' ? value
                : value ? parseInt(value) : null;
            const response = await fetch(`${API_BASE}/admin/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    [settingKey]: parsed
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
