/**
 * Admin page functionality
 */

// API_BASE is defined in api.js which is loaded before this script

const admin = {
    servers: [],
    collections: [],
    adminSettings: {},
    availableModels: [],
    serverStatuses: {},
    statusPollingInterval: null,
    currentLogServerId: null,
    activityLogState: { offset: 0, limit: 50, total: 0, action_type: '', user_ip: '', search: '' },

    /**
     * Initialize admin page
     */
    async init() {
        // Auth check: require admin
        try {
            const mode = await api.getAuthMode();
            if (!mode.single_user) {
                const user = await api.getCurrentUser();
                if (!user) { window.location.href = '/login'; return; }
                if (user.usertype !== 'admin') { window.location.href = '/'; return; }
            }
        } catch (e) {
            console.error('Auth check failed:', e);
        }

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

        // Log viewer event listeners
        document.getElementById('close-log-viewer-modal').addEventListener('click', () => {
            this.closeLogViewer();
        });
        document.getElementById('log-viewer-modal-overlay').addEventListener('click', () => {
            this.closeLogViewer();
        });
        document.getElementById('log-refresh-btn').addEventListener('click', () => {
            this.refreshLog();
        });

        // Activity log event listeners
        document.getElementById('activity-log-btn').addEventListener('click', () => {
            this.openActivityLogModal();
        });
        document.getElementById('close-activity-log-modal').addEventListener('click', () => {
            this.closeActivityLogModal();
        });
        document.getElementById('activity-log-modal-overlay').addEventListener('click', () => {
            this.closeActivityLogModal();
        });

        const logDebounce = this.debounce(() => this.loadActivityLog(), 300);
        document.getElementById('activity-log-search').addEventListener('input', (e) => {
            this.activityLogState.search = e.target.value;
            this.activityLogState.offset = 0;
            logDebounce();
        });
        document.getElementById('activity-log-action-type').addEventListener('change', (e) => {
            this.activityLogState.action_type = e.target.value;
            this.activityLogState.offset = 0;
            this.loadActivityLog();
        });
        document.getElementById('activity-log-ip').addEventListener('input', (e) => {
            this.activityLogState.user_ip = e.target.value;
            this.activityLogState.offset = 0;
            logDebounce();
        });

        // Close modal on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeServerModal();
                this.closeCollectionModal();
                this.closeSystemInfoModal();
                this.closeLogViewer();
                this.closeActivityLogModal();
                this.closeModal('usage-modal');
                this.closeModal('file-info-modal');
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
        document.getElementById('chat-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('chat_server_id', e.target.value);
        });
        document.getElementById('translation-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('translation_server_id', e.target.value);
        });

        // Vault server dropdowns
        document.getElementById('vault-image-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('vault_image_server_id', e.target.value);
        });
        document.getElementById('vault-text-server').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('vault_text_server_id', e.target.value);
        });
        document.getElementById('vault-chat-records').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('vault_chat_records', e.target.value);
        });

        // Skip contextual retrieval checkbox
        document.getElementById('skip-contextual-retrieval').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('skip_contextual_retrieval', e.target.checked);
        });

        // Whisper model dropdown
        document.getElementById('whisper-model').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('whisper_model', e.target.value);
        });

        // Date format dropdown
        document.getElementById('date-format-select').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('date_format', e.target.value);
        });

        // System Info button
        document.getElementById('system-info-btn').addEventListener('click', () => {
            this.openSystemInfoModal();
        });
        document.getElementById('close-system-info-modal').addEventListener('click', () => {
            this.closeSystemInfoModal();
        });
        document.getElementById('system-info-modal-overlay').addEventListener('click', () => {
            this.closeSystemInfoModal();
        });

        // Restart ULF Web button
        document.getElementById('restart-ulfweb-btn').addEventListener('click', () => {
            this.restartUlfWeb();
        });

        // Single user mode dropdown
        document.getElementById('single-user-select').addEventListener('change', (e) => {
            this.saveDocumentAiSetting('single_user', e.target.value);
        });

        // Usage
        document.getElementById('usage-btn').addEventListener('click', () => this.openUsageModal());
        document.getElementById('close-usage-modal').addEventListener('click', () => this.closeModal('usage-modal'));
        document.getElementById('usage-modal-overlay').addEventListener('click', () => this.closeModal('usage-modal'));

        // File info
        document.getElementById('file-info-btn').addEventListener('click', () => this.openFileInfoModal());
        document.getElementById('close-file-info-modal').addEventListener('click', () => this.closeModal('file-info-modal'));
        document.getElementById('file-info-modal-overlay').addEventListener('click', () => this.closeModal('file-info-modal'));

        // User management
        document.getElementById('user-mgmt-btn').addEventListener('click', () => this.openUserMgmtModal());
        document.getElementById('close-user-mgmt-modal').addEventListener('click', () => this.closeModal('user-mgmt-modal'));
        document.getElementById('user-mgmt-modal-overlay').addEventListener('click', () => this.closeModal('user-mgmt-modal'));

        document.getElementById('add-user-btn').addEventListener('click', () => this.openUserEditModal());
        document.getElementById('close-user-edit-modal').addEventListener('click', () => this.closeModal('user-edit-modal'));
        document.getElementById('user-edit-modal-overlay').addEventListener('click', () => this.closeModal('user-edit-modal'));
        document.getElementById('save-user-btn').addEventListener('click', () => this.saveUser());

        document.getElementById('close-set-password-modal').addEventListener('click', () => this.closeModal('set-password-modal'));
        document.getElementById('set-password-modal-overlay').addEventListener('click', () => this.closeModal('set-password-modal'));
        document.getElementById('save-set-password-btn').addEventListener('click', () => this.saveSetPassword());
    },

    closeModal(id) {
        document.getElementById(id).classList.add('hidden');
    },

    async openUserMgmtModal() {
        document.getElementById('user-mgmt-modal').classList.remove('hidden');
        await this.loadUsers();
    },

    async loadUsers() {
        try {
            const users = await api.listUsers();
            const tbody = document.getElementById('user-mgmt-tbody');
            tbody.innerHTML = users.map(u => `
                <tr>
                    <td>${this.escapeHtml(u.username)}</td>
                    <td>${u.usertype}</td>
                    <td>${this.escapeHtml(u.full_name || '')}</td>
                    <td>
                        <button class="action-btn" onclick="admin.openUserEditModal(${u.id})">Edit</button>
                        <button class="action-btn" onclick="admin.openSetPasswordModal(${u.id}, '${this.escapeHtml(u.username)}')">Password</button>
                        <button class="action-btn delete-btn" onclick="admin.deleteUser(${u.id}, '${this.escapeHtml(u.username)}')">Delete</button>
                    </td>
                </tr>
            `).join('');
        } catch (e) {
            console.error('Failed to load users:', e);
        }
    },

    async openUserEditModal(userId) {
        const modal = document.getElementById('user-edit-modal');
        const title = document.getElementById('user-edit-modal-title');
        const passwordGroup = document.getElementById('user-edit-password-group');
        document.getElementById('user-edit-error').textContent = '';

        if (userId) {
            title.textContent = 'Edit User';
            passwordGroup.style.display = 'none';
            try {
                const users = await api.listUsers();
                const user = users.find(u => u.id === userId);
                if (user) {
                    document.getElementById('user-edit-id').value = user.id;
                    document.getElementById('user-edit-username').value = user.username;
                    document.getElementById('user-edit-fullname').value = user.full_name || '';
                    document.getElementById('user-edit-type').value = user.usertype;
                }
            } catch (e) {
                console.error('Failed to load user:', e);
            }
        } else {
            title.textContent = 'Add User';
            passwordGroup.style.display = '';
            document.getElementById('user-edit-id').value = '';
            document.getElementById('user-edit-username').value = '';
            document.getElementById('user-edit-password').value = '';
            document.getElementById('user-edit-fullname').value = '';
            document.getElementById('user-edit-type').value = 'normal';
        }
        modal.classList.remove('hidden');
    },

    async saveUser() {
        const errorEl = document.getElementById('user-edit-error');
        const userId = document.getElementById('user-edit-id').value;
        const username = document.getElementById('user-edit-username').value.trim();
        const fullName = document.getElementById('user-edit-fullname').value.trim();
        const usertype = document.getElementById('user-edit-type').value;
        errorEl.textContent = '';

        if (!username) { errorEl.textContent = 'Username is required'; return; }

        try {
            if (userId) {
                await api.updateUser(parseInt(userId), { username, full_name: fullName, usertype });
            } else {
                const password = document.getElementById('user-edit-password').value;
                if (!password) { errorEl.textContent = 'Password is required'; return; }
                await api.createUser({ username, password, full_name: fullName, usertype });
            }
            this.closeModal('user-edit-modal');
            await this.loadUsers();
            // Refresh single-user dropdown
            this.populateSingleUserDropdown();
        } catch (e) {
            errorEl.textContent = e.message;
        }
    },

    async deleteUser(userId, username) {
        if (!confirm(`Delete user "${username}"?`)) return;
        try {
            await api.deleteUser(userId);
            await this.loadUsers();
            this.populateSingleUserDropdown();
        } catch (e) {
            alert(e.message);
        }
    },

    openSetPasswordModal(userId, username) {
        document.getElementById('set-password-user-id').value = userId;
        document.getElementById('set-password-title').textContent = `Set Password: ${username}`;
        document.getElementById('set-password-value').value = '';
        document.getElementById('set-password-error').textContent = '';
        document.getElementById('set-password-modal').classList.remove('hidden');
    },

    async saveSetPassword() {
        const userId = document.getElementById('set-password-user-id').value;
        const password = document.getElementById('set-password-value').value;
        const errorEl = document.getElementById('set-password-error');
        errorEl.textContent = '';

        if (!password) { errorEl.textContent = 'Password is required'; return; }

        try {
            await api.setUserPassword(parseInt(userId), password);
            this.closeModal('set-password-modal');
        } catch (e) {
            errorEl.textContent = e.message;
        }
    },

    async populateSingleUserDropdown() {
        try {
            const users = await api.listUsers();
            const select = document.getElementById('single-user-select');
            const currentValue = this.adminSettings.single_user || '';
            select.innerHTML = '<option value="">Disabled (login required)</option>';
            for (const u of users) {
                const option = document.createElement('option');
                option.value = u.username;
                option.textContent = `${u.username} (${u.usertype})`;
                if (u.username === currentValue) option.selected = true;
                select.appendChild(option);
            }
        } catch (e) {
            console.error('Failed to populate single user dropdown:', e);
        }
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
                    ${hasModel ? `<button class="log-btn" onclick="admin.openLogViewer(${server.id})">View Log</button>` : ''}
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

        if (!name) {
            alert('Please fill in the server name');
            return;
        }

        const data = {
            friendly_name: name,
            url: url || undefined,
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
            { id: 'document-ai-understanding-server', setting: 'document_ai_understanding_server_id' },
            { id: 'chat-server', setting: 'chat_server_id' },
            { id: 'translation-server', setting: 'translation_server_id' },
            { id: 'vault-image-server', setting: 'vault_image_server_id' },
            { id: 'vault-text-server', setting: 'vault_text_server_id' }
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

        // Set whisper model dropdown
        const whisperSelect = document.getElementById('whisper-model');
        if (whisperSelect && this.adminSettings.whisper_model) {
            whisperSelect.value = this.adminSettings.whisper_model;
        }

        // Set vault chat records dropdown
        const vaultChatRecords = document.getElementById('vault-chat-records');
        if (vaultChatRecords && this.adminSettings.vault_chat_records != null) {
            vaultChatRecords.value = this.adminSettings.vault_chat_records;
        }

        // Set date format dropdown
        const dateFormatSelect = document.getElementById('date-format-select');
        if (dateFormatSelect && this.adminSettings.date_format) {
            dateFormatSelect.value = this.adminSettings.date_format;
        }

        // Populate single-user dropdown
        this.populateSingleUserDropdown();
    },

    /**
     * Restart the ULF Web server
     */
    async restartUlfWeb() {
        if (!confirm('Restart ULF Web server? All active connections will be interrupted.')) {
            return;
        }

        const btn = document.getElementById('restart-ulfweb-btn');
        btn.disabled = true;
        btn.textContent = 'Restarting...';

        try {
            await fetch(`${API_BASE}/admin/restart`, { method: 'POST' });
        } catch (error) {
            // Expected - server is restarting
        }

        // Poll /health until the server is back up
        const pollHealth = () => {
            setTimeout(async () => {
                try {
                    const response = await fetch('/health');
                    if (response.ok) {
                        window.location.reload();
                        return;
                    }
                } catch (e) {
                    // Server still down
                }
                pollHealth();
            }, 1000);
        };

        // Wait a moment before starting to poll
        setTimeout(pollHealth, 1500);
    },

    /**
     * Save Document AI server setting
     */
    async saveDocumentAiSetting(settingKey, value) {
        try {
            // Server IDs are strings from dropdowns — parse to int or null
            // Booleans (e.g. skip_contextual_retrieval) pass through as-is
            // String settings (e.g. whisper_model) pass through as-is
            const stringSettings = ['whisper_model', 'date_format'];
            const intSettings = ['vault_chat_records'];
            let parsed;
            if (typeof value === 'boolean') {
                parsed = value;
            } else if (stringSettings.includes(settingKey)) {
                parsed = value || null;
            } else if (intSettings.includes(settingKey)) {
                parsed = parseInt(value);
            } else {
                parsed = value ? parseInt(value) : null;
            }
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
    },

    // Log viewer methods

    async openLogViewer(serverId) {
        const server = this.servers.find(s => s.id === serverId);
        if (!server) return;

        this.currentLogServerId = serverId;
        const modal = document.getElementById('log-viewer-modal');
        const title = document.getElementById('log-viewer-title');
        const body = document.getElementById('log-viewer-body');

        title.textContent = `Log: ${server.friendly_name}`;
        body.textContent = 'Loading...';
        modal.classList.remove('hidden');

        try {
            const response = await fetch(`${API_BASE}/admin/servers/${serverId}/log`);
            if (!response.ok) throw new Error('Failed to fetch log');
            const data = await response.json();
            body.textContent = data.log || 'No log output yet.';
            body.scrollTop = body.scrollHeight;
        } catch (error) {
            console.error('Failed to load log:', error);
            body.textContent = 'Failed to load log.';
        }
    },

    closeLogViewer() {
        document.getElementById('log-viewer-modal').classList.add('hidden');
        this.currentLogServerId = null;
    },

    async refreshLog() {
        if (!this.currentLogServerId) return;
        const body = document.getElementById('log-viewer-body');

        try {
            const response = await fetch(`${API_BASE}/admin/servers/${this.currentLogServerId}/log`);
            if (!response.ok) throw new Error('Failed to fetch log');
            const data = await response.json();
            body.textContent = data.log || 'No log output yet.';
            body.scrollTop = body.scrollHeight;
        } catch (error) {
            console.error('Failed to refresh log:', error);
        }
    },

    // System Info methods

    async openSystemInfoModal() {
        const modal = document.getElementById('system-info-modal');
        const body = document.getElementById('system-info-body');
        body.innerHTML = '<p>Loading...</p>';
        modal.classList.remove('hidden');

        try {
            const response = await fetch(`${API_BASE}/admin/system-info`);
            if (!response.ok) throw new Error('Failed to fetch system info');
            const data = await response.json();
            this.renderSystemInfo(data);
        } catch (error) {
            console.error('Failed to load system info:', error);
            body.innerHTML = `<p style="color: var(--error);">Failed to load system info.</p>`;
        }
    },

    closeSystemInfoModal() {
        document.getElementById('system-info-modal').classList.add('hidden');
    },

    renderSystemInfo(data) {
        const body = document.getElementById('system-info-body');
        let html = '';

        // RAM section
        html += '<h3 class="sysinfo-section-title">System RAM</h3>';
        html += this.renderMemoryBar(data.ram.used, data.ram.total);
        html += `<div class="sysinfo-details">
            <span>Used: ${this.formatBytes(data.ram.used)}</span>
            <span>Available: ${this.formatBytes(data.ram.available)}</span>
            <span>Total: ${this.formatBytes(data.ram.total)}</span>
        </div>`;

        // VRAM section
        html += '<h3 class="sysinfo-section-title">GPU VRAM</h3>';
        if (data.gpu) {
            html += this.renderMemoryBar(data.gpu.used, data.gpu.total);
            html += `<div class="sysinfo-details">
                <span>Used: ${this.formatBytes(data.gpu.used)}</span>
                <span>Free: ${this.formatBytes(data.gpu.free)}</span>
                <span>Total: ${this.formatBytes(data.gpu.total)}</span>
            </div>`;
        } else {
            html += '<p class="sysinfo-none">No GPU detected</p>';
        }

        // Models section
        html += '<h3 class="sysinfo-section-title">Loaded Models</h3>';
        if (data.models.length === 0) {
            html += '<p class="sysinfo-none">No models loaded</p>';
        } else {
            for (const model of data.models) {
                const modeLabels = {
                    vram_only: 'VRAM only',
                    vram_and_ram: 'VRAM + RAM',
                    ram_only: 'RAM only'
                };
                const modeLabel = modeLabels[model.memory_mode] || model.memory_mode;

                html += `<div class="sysinfo-model-item">
                    <div class="sysinfo-model-header">
                        <span class="sysinfo-model-name">${this.escapeHtml(model.server_name)}</span>
                        <span class="sysinfo-mode-badge ${model.memory_mode}">${modeLabel}</span>
                    </div>
                    <div class="sysinfo-model-file">${this.escapeHtml(model.model_file || 'Unknown')}</div>
                    <div class="sysinfo-model-stats">
                        <span>RAM: ${this.formatBytes(model.ram_bytes)}</span>
                        ${model.vram_bytes > 0 ? `<span>VRAM: ${this.formatBytes(model.vram_bytes)}</span>` : ''}
                        ${model.gtt_bytes > 0 ? `<span>GTT: ${this.formatBytes(model.gtt_bytes)}</span>` : ''}
                    </div>
                </div>`;
            }
        }

        body.innerHTML = html;
    },

    renderMemoryBar(used, total) {
        if (total === 0) return '';
        const pct = Math.round((used / total) * 100);
        let colorClass = 'green';
        if (pct >= 90) colorClass = 'red';
        else if (pct >= 70) colorClass = 'amber';

        return `<div class="sysinfo-bar-container">
            <div class="sysinfo-bar ${colorClass}" style="width: ${pct}%"></div>
        </div>`;
    },

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        const val = bytes / Math.pow(1024, i);
        return `${val.toFixed(1)} ${units[i]}`;
    },

    // Activity log methods

    debounce(fn, delay) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    },

    async openActivityLogModal() {
        const modal = document.getElementById('activity-log-modal');
        modal.classList.remove('hidden');
        this.activityLogState.offset = 0;
        await this.loadActionTypes();
        await this.loadActivityLog();
    },

    closeActivityLogModal() {
        document.getElementById('activity-log-modal').classList.add('hidden');
    },

    async loadActionTypes() {
        try {
            const response = await fetch(`${API_BASE}/admin/activity-log/action-types`);
            if (!response.ok) return;
            const data = await response.json();
            const select = document.getElementById('activity-log-action-type');
            const current = select.value;
            select.innerHTML = '<option value="">All actions</option>';
            for (const type of data.action_types) {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type;
                select.appendChild(option);
            }
            select.value = current;
        } catch (error) {
            console.error('Failed to load action types:', error);
        }
    },

    async loadActivityLog() {
        const s = this.activityLogState;
        const params = new URLSearchParams({ offset: s.offset, limit: s.limit });
        if (s.action_type) params.set('action_type', s.action_type);
        if (s.user_ip) params.set('user_ip', s.user_ip);
        if (s.search) params.set('search', s.search);

        try {
            const response = await fetch(`${API_BASE}/admin/activity-log?${params}`);
            if (!response.ok) throw new Error('Failed to fetch activity log');
            const data = await response.json();
            s.total = data.total;
            this.renderActivityLog(data.entries);
            this.renderActivityLogPagination();
        } catch (error) {
            console.error('Failed to load activity log:', error);
            document.getElementById('activity-log-tbody').innerHTML =
                '<tr><td colspan="4" class="activity-log-empty">Failed to load activity log.</td></tr>';
        }
    },

    renderActivityLog(entries) {
        const tbody = document.getElementById('activity-log-tbody');
        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="activity-log-empty">No activity found.</td></tr>';
            return;
        }

        tbody.innerHTML = entries.map(entry => {
            const date = new Date(entry.created_at + 'Z');
            const time = date.toLocaleString();
            return `<tr>
                <td class="activity-log-time">${this.escapeHtml(time)}</td>
                <td class="activity-log-ip">${this.escapeHtml(entry.user_ip)}</td>
                <td><span class="activity-log-badge">${this.escapeHtml(entry.action_type)}</span></td>
                <td>${this.escapeHtml(entry.description)}</td>
            </tr>`;
        }).join('');
    },

    renderActivityLogPagination() {
        const s = this.activityLogState;
        const container = document.getElementById('activity-log-pagination');
        const totalPages = Math.ceil(s.total / s.limit);
        const currentPage = Math.floor(s.offset / s.limit) + 1;

        if (totalPages <= 1) {
            container.innerHTML = s.total > 0 ? `<span class="activity-log-total">${s.total} entries</span>` : '';
            return;
        }

        container.innerHTML = `
            <button class="activity-log-page-btn" ${currentPage <= 1 ? 'disabled' : ''} onclick="admin.activityLogPage(${s.offset - s.limit})">Previous</button>
            <span class="activity-log-page-info">Page ${currentPage} of ${totalPages} (${s.total} entries)</span>
            <button class="activity-log-page-btn" ${currentPage >= totalPages ? 'disabled' : ''} onclick="admin.activityLogPage(${s.offset + s.limit})">Next</button>
        `;
    },

    activityLogPage(newOffset) {
        this.activityLogState.offset = Math.max(0, newOffset);
        this.loadActivityLog();
    },

    async openUsageModal() {
        document.getElementById('usage-modal').classList.remove('hidden');
        document.getElementById('usage-body').innerHTML = '<p>Loading...</p>';
        try {
            const res = await fetch(`${API_BASE}/admin/usage`);
            if (!res.ok) throw new Error('Failed to load usage stats');
            const data = await res.json();
            this.renderUsageStats(data);
        } catch (e) {
            document.getElementById('usage-body').innerHTML = `<p style="color:var(--error)">Error: ${this.escapeHtml(e.message)}</p>`;
        }
    },

    renderUsageCard(label, value) {
        return `<div class="usage-card">
            <div class="usage-card-value">${this.escapeHtml(String(value))}</div>
            <div class="usage-card-label">${this.escapeHtml(label)}</div>
        </div>`;
    },

    renderUsageStats(data) {
        const body = document.getElementById('usage-body');
        const s = data.summary;
        let html = '';

        // Summary cards
        html += '<div class="usage-cards">';
        html += this.renderUsageCard('Total Users', s.total_users);
        html += this.renderUsageCard('Active (30d)', s.active_users);
        html += this.renderUsageCard('Conversations', s.total_conversations);
        html += this.renderUsageCard('Messages', s.total_messages);
        html += this.renderUsageCard('Documents', s.total_documents);
        html += this.renderUsageCard('Vault Cases', s.total_vault_cases);
        html += '</div>';

        // Messages per day chart
        if (data.messages_per_day.length > 0) {
            html += '<h3 class="usage-section-title">Messages per Day (Last 30 Days)</h3>';
            const maxCount = Math.max(...data.messages_per_day.map(d => d.count));
            html += '<div class="usage-chart">';
            for (const d of data.messages_per_day) {
                const pct = maxCount > 0 ? (d.count / maxCount) * 100 : 0;
                const label = d.day.slice(5); // MM-DD
                html += `<div class="usage-chart-bar-wrap" title="${this.escapeHtml(d.day)}: ${d.count}">
                    <div class="usage-chart-bar" style="height:${pct}%"></div>
                    <div class="usage-chart-label">${this.escapeHtml(label)}</div>
                </div>`;
            }
            html += '</div>';
        }

        // Per-user table
        if (data.per_user.length > 0) {
            html += '<h3 class="usage-section-title">Per-User Breakdown</h3>';
            html += '<div class="activity-log-table-wrap"><table class="activity-log-table"><thead><tr>';
            html += '<th>Username</th><th>Conversations</th><th>Messages</th><th>Last Active</th>';
            html += '</tr></thead><tbody>';
            for (const u of data.per_user) {
                const lastActive = u.last_active ? new Date(u.last_active + 'Z').toLocaleString() : '-';
                html += `<tr>
                    <td>${this.escapeHtml(u.username)}</td>
                    <td>${u.conversation_count}</td>
                    <td>${u.message_count}</td>
                    <td class="activity-log-time">${this.escapeHtml(lastActive)}</td>
                </tr>`;
            }
            html += '</tbody></table></div>';
        }

        // Feature usage
        if (data.feature_usage.length > 0) {
            html += '<h3 class="usage-section-title">Feature Usage</h3>';
            // Group by prefix (part before first '.')
            const groups = {};
            for (const f of data.feature_usage) {
                const dotIdx = f.action_type.indexOf('.');
                const prefix = dotIdx > 0 ? f.action_type.slice(0, dotIdx) : f.action_type;
                if (!groups[prefix]) groups[prefix] = { total: 0, items: [] };
                groups[prefix].total += f.count;
                groups[prefix].items.push(f);
            }
            html += '<div class="usage-feature-grid">';
            for (const [name, group] of Object.entries(groups)) {
                html += `<div class="usage-feature-card">
                    <div class="usage-feature-name">${this.escapeHtml(name)}</div>
                    <div class="usage-feature-count">${group.total}</div>`;
                for (const item of group.items) {
                    html += `<div class="usage-feature-detail">${this.escapeHtml(item.action_type)} <span>${item.count}</span></div>`;
                }
                html += '</div>';
            }
            html += '</div>';
        }

        body.innerHTML = html;
    },

    formatAge(seconds) {
        const days = Math.floor(seconds / 86400);
        if (days > 365) return Math.floor(days / 365) + 'y ' + (days % 365) + 'd';
        if (days > 0) return days + 'd';
        const hours = Math.floor(seconds / 3600);
        if (hours > 0) return hours + 'h';
        return Math.floor(seconds / 60) + 'm';
    },

    formatDate(iso) {
        const d = new Date(iso);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    renderFileTable(title, files) {
        if (files.length === 0) return '';
        let html = `<h3 class="fileinfo-subtitle">${this.escapeHtml(title)}</h3>`;
        html += '<table class="fileinfo-table"><thead><tr><th>File</th><th>Size</th><th>Modified</th><th>Age</th></tr></thead><tbody>';
        for (const f of files) {
            html += `<tr>
                <td class="fileinfo-name">${this.escapeHtml(f.name)}</td>
                <td class="fileinfo-size">${this.formatBytes(f.size_bytes)}</td>
                <td class="fileinfo-date">${this.formatDate(f.modified)}</td>
                <td class="fileinfo-age">${this.formatAge(f.age_seconds)}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        return html;
    },

    /**
     * Open file information modal (project and model files)
     */
    async openFileInfoModal() {
        document.getElementById('file-info-modal').classList.remove('hidden');
        const container = document.getElementById('file-info-body');
        container.innerHTML = '<p>Loading...</p>';
        try {
            const resp = await fetch(`${API_BASE}/admin/file-info`);
            if (!resp.ok) throw new Error('Failed to load file info');
            const data = await resp.json();

            let html = this.renderFileTable('Model Files', data.model_files)
                     + this.renderFileTable('Project Files', data.project_files);

            if (!html) html = '<p class="setting-hint">No files found.</p>';
            container.innerHTML = html;
        } catch (e) {
            console.error('Failed to load file info:', e);
            container.innerHTML = '<p class="setting-hint">Failed to load file information.</p>';
        }
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => admin.init());
