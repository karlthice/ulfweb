/**
 * Vault functionality - case records management
 */

const vault = {
    cases: [],
    currentCase: null,
    searchQuery: '',
    dateFormat: 'YYYY-MM-DD',

    async init() {
        this.setupEventListeners();
        this.dateFormat = await api.getDateFormat();
    },

    setupEventListeners() {
        document.getElementById('vault-new-case-btn').addEventListener('click', () => this.showCreateForm());
        document.getElementById('vault-search-input').addEventListener('input', (e) => this.handleSearch(e.target.value));
        document.getElementById('vault-back-btn').addEventListener('click', () => this.showCaseList());
    },

    /**
     * Load and display the case list
     */
    async loadCases() {
        try {
            this.cases = await api.listVaultCases();
            this.renderCaseList();
        } catch (error) {
            console.error('Failed to load vault cases:', error);
        }
    },

    /**
     * Render the case list view
     */
    renderCaseList() {
        const list = document.getElementById('vault-case-list');
        const filtered = this.searchQuery
            ? this.cases.filter(c =>
                c.name.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
                c.identifier.toLowerCase().includes(this.searchQuery.toLowerCase()))
            : this.cases;

        if (filtered.length === 0) {
            list.innerHTML = '<div class="vault-empty">No cases found. Create one to get started.</div>';
            return;
        }

        list.innerHTML = filtered.map(c => `
            <div class="vault-case-item" data-id="${c.id}">
                <div class="vault-case-info">
                    <div class="vault-case-name">${this.escapeHtml(c.name)}</div>
                    <div class="vault-case-meta">
                        <span class="vault-case-id">${this.escapeHtml(c.identifier)}</span>
                        <span class="vault-status-badge vault-status-${c.status}">${c.status}</span>
                        ${c.is_public ? '<span class="vault-public-badge">public</span>' : ''}
                    </div>
                </div>
                <div class="vault-case-date">${this.formatDate(c.updated_at)}</div>
            </div>
        `).join('');

        // Add click handlers
        list.querySelectorAll('.vault-case-item').forEach(item => {
            item.addEventListener('click', () => this.openCase(parseInt(item.dataset.id)));
        });
    },

    handleSearch(query) {
        this.searchQuery = query;
        if (this.currentCase) {
            // Search within current case records
            this.renderRecordList();
        } else {
            this.renderCaseList();
        }
    },

    /**
     * Show the create case form
     */
    showCreateForm() {
        const list = document.getElementById('vault-case-list');
        const existing = document.getElementById('vault-create-form');
        if (existing) {
            existing.remove();
            return;
        }

        const form = document.createElement('div');
        form.id = 'vault-create-form';
        form.className = 'vault-create-form';
        form.innerHTML = `
            <input type="text" id="vault-new-identifier" placeholder="Identifier (e.g., initials, ID)" required>
            <input type="text" id="vault-new-name" placeholder="Display name" required>
            <textarea id="vault-new-description" placeholder="Description (optional)" rows="2"></textarea>
            <div class="vault-form-row">
                <select id="vault-new-visibility" class="vault-status-select">
                    <option value="private" selected>Private</option>
                    <option value="public">Public</option>
                </select>
                <div class="vault-form-actions">
                    <button class="vault-btn vault-btn-secondary" id="vault-create-cancel">Cancel</button>
                    <button class="vault-btn vault-btn-primary" id="vault-create-submit">Create</button>
                </div>
            </div>
        `;

        list.insertBefore(form, list.firstChild);

        document.getElementById('vault-create-cancel').addEventListener('click', () => form.remove());
        document.getElementById('vault-create-submit').addEventListener('click', () => this.createCase());
        document.getElementById('vault-new-name').focus();
    },

    async createCase() {
        const identifier = document.getElementById('vault-new-identifier').value.trim();
        const name = document.getElementById('vault-new-name').value.trim();
        const description = document.getElementById('vault-new-description').value.trim();
        const isPublic = document.getElementById('vault-new-visibility').value === 'public';

        if (!identifier || !name) {
            alert('Identifier and name are required.');
            return;
        }

        try {
            await api.createVaultCase({ identifier, name, description, is_public: isPublic });
            const form = document.getElementById('vault-create-form');
            if (form) form.remove();
            await this.loadCases();
        } catch (error) {
            alert('Failed to create case: ' + error.message);
        }
    },

    /**
     * Open a case detail view
     */
    async openCase(caseId) {
        try {
            const caseData = await api.getVaultCase(caseId);
            if (!caseData) {
                alert('Case not found');
                return;
            }
            this.currentCase = caseData;
            this.currentUserId = caseData.current_user_id;
            this.showCaseDetail();
        } catch (error) {
            console.error('Failed to open case:', error);
        }
    },

    /**
     * Show case list view
     */
    showCaseList() {
        this.currentCase = null;
        this.searchQuery = '';
        document.getElementById('vault-search-input').value = '';
        document.getElementById('vault-list-view').classList.remove('hidden');
        document.getElementById('vault-detail-view').classList.add('hidden');
        document.getElementById('vault-new-case-btn').classList.remove('hidden');
        document.getElementById('vault-back-btn').classList.add('hidden');
        document.getElementById('vault-search-input').placeholder = 'Search cases...';
        this.loadCases();
    },

    /**
     * Show case detail view
     */
    showCaseDetail() {
        const c = this.currentCase;
        document.getElementById('vault-list-view').classList.add('hidden');
        document.getElementById('vault-detail-view').classList.remove('hidden');
        document.getElementById('vault-new-case-btn').classList.add('hidden');
        document.getElementById('vault-back-btn').classList.remove('hidden');
        document.getElementById('vault-search-input').placeholder = 'Search records...';
        document.getElementById('vault-search-input').value = '';
        this.searchQuery = '';

        // Render case header
        const header = document.getElementById('vault-case-header');
        header.innerHTML = `
            <div class="vault-detail-title">
                <h3>${this.escapeHtml(c.name)}</h3>
                <span class="vault-case-id">${this.escapeHtml(c.identifier)}</span>
                <span class="vault-status-badge vault-status-${c.status}">${c.status}</span>
                ${c.is_public ? '<span class="vault-public-badge">public</span>' : ''}
                ${c.owner_ip ? `<span class="vault-owner-badge">Owner: ${this.escapeHtml(c.owner_ip)}</span>` : ''}
            </div>
            ${c.description ? `<p class="vault-detail-desc">${this.escapeHtml(c.description)}</p>` : ''}
            ${c.ai_summary ? `<div class="vault-case-summary"><strong>AI Summary</strong><p>${this.escapeHtml(c.ai_summary)}</p></div>` : ''}
            <div class="vault-detail-actions">
                <button class="vault-btn vault-btn-primary" id="vault-add-record-btn">Add Record</button>
                <select id="vault-status-select" class="vault-status-select">
                    <option value="active" ${c.status === 'active' ? 'selected' : ''}>Active</option>
                    <option value="closed" ${c.status === 'closed' ? 'selected' : ''}>Closed</option>
                    <option value="archived" ${c.status === 'archived' ? 'selected' : ''}>Archived</option>
                </select>
                <select id="vault-visibility-select" class="vault-status-select">
                    <option value="private" ${!c.is_public ? 'selected' : ''}>Private</option>
                    <option value="public" ${c.is_public ? 'selected' : ''}>Public</option>
                </select>
                <button class="vault-btn vault-btn-danger" id="vault-delete-case-btn">Delete Case</button>
                <button class="vault-btn vault-btn-chat" id="vault-chat-case-btn">Chat</button>
            </div>
        `;

        document.getElementById('vault-add-record-btn').addEventListener('click', () => this.showAddRecordForm());
        document.getElementById('vault-status-select').addEventListener('change', (e) => this.updateCaseStatus(e.target.value));
        document.getElementById('vault-visibility-select').addEventListener('change', (e) => this.updateCaseVisibility(e.target.value));
        document.getElementById('vault-delete-case-btn').addEventListener('click', () => this.deleteCase());
        document.getElementById('vault-chat-case-btn').addEventListener('click', () => this.chatAboutCase());

        this.renderRecordList();
    },

    async updateCaseStatus(status) {
        try {
            await api.updateVaultCase(this.currentCase.id, { status });
            this.currentCase.status = status;
        } catch (error) {
            console.error('Failed to update status:', error);
        }
    },

    async updateCaseVisibility(value) {
        const isPublic = value === 'public';
        try {
            await api.updateVaultCase(this.currentCase.id, { is_public: isPublic });
            this.currentCase.is_public = isPublic;
        } catch (error) {
            console.error('Failed to update visibility:', error);
        }
    },

    async deleteCase() {
        if (!confirm(`Delete case "${this.currentCase.name}" and all its records? This cannot be undone.`)) return;
        try {
            await api.deleteVaultCase(this.currentCase.id);
            this.showCaseList();
        } catch (error) {
            alert('Failed to delete case: ' + error.message);
        }
    },

    async chatAboutCase() {
        const c = this.currentCase;
        if (!c) return;

        // Switch to chat tab
        document.getElementById('chat-tab').click();

        // Always start a new conversation for vault case chats
        await conversations.create();

        // Pre-fill @mention with case name and track the case ref
        const input = document.getElementById('message-input');
        input.value = `@${c.name} `;
        input.focus();
        if (!chat.caseRefs.includes(c.id)) {
            chat.caseRefs.push(c.id);
        }
    },

    /**
     * Render the record list in case detail view
     */
    renderRecordList() {
        const container = document.getElementById('vault-record-list');
        let records = this.currentCase.records || [];

        if (this.searchQuery) {
            const q = this.searchQuery.toLowerCase();
            records = records.filter(r =>
                (r.title && r.title.toLowerCase().includes(q)) ||
                (r.content && r.content.toLowerCase().includes(q)) ||
                (r.ai_description && r.ai_description.toLowerCase().includes(q))
            );
        }

        if (records.length === 0) {
            container.innerHTML = '<div class="vault-empty">No records yet. Add one to get started.</div>';
            return;
        }

        container.innerHTML = records.map(r => `
            <div class="vault-record-item" data-id="${r.id}">
                <button class="vault-star-btn ${r.starred ? 'starred' : ''}" data-id="${r.id}" title="Toggle star">
                    ${r.starred ? '&#9733;' : '&#9734;'}
                </button>
                <span class="vault-record-type-icon">${this.getTypeIcon(r.record_type)}</span>
                <div class="vault-record-info">
                    <div class="vault-record-title">${this.escapeHtml(r.title || 'Untitled')}</div>
                    <div class="vault-record-meta">
                        ${this.formatDate(r.record_date)} &middot; ${r.record_type}
                        ${r.created_by_ip ? ` &middot; ${this.escapeHtml(r.created_by_ip)}` : ''}
                        ${r.original_filename ? ` &middot; ${this.escapeHtml(r.original_filename)}` : ''}
                        ${r.file_size ? ` (${this.formatSize(r.file_size)})` : ''}
                    </div>
                    ${r.content ? (r.content.length > 150 ? `
                        <details class="vault-record-expandable">
                            <summary class="vault-record-snippet">${this.escapeHtml(r.content.substring(0, 150))}...</summary>
                            <div class="vault-record-full-content">${this.escapeHtml(r.content)}</div>
                        </details>
                    ` : `<div class="vault-record-snippet">${this.escapeHtml(r.content)}</div>`) : ''}
                    ${r.ai_description ? `
                        <details class="vault-ai-desc">
                            <summary>AI Description</summary>
                            <div>${this.escapeHtml(r.ai_description)}</div>
                        </details>
                    ` : ''}
                </div>
                <div class="vault-record-actions">
                    ${this.isEditableRecord(r) ? `<button class="vault-btn vault-btn-small vault-edit-record" data-id="${r.id}">Edit</button>` : ''}
                    ${r.filename ? `<a href="${api.getVaultRecordFileUrl(r.id)}" class="vault-btn vault-btn-small" download>Download</a>` : ''}
                    <button class="vault-btn vault-btn-small vault-btn-danger vault-delete-record" data-id="${r.id}">Delete</button>
                </div>
            </div>
        `).join('');

        // Star toggle handlers
        container.querySelectorAll('.vault-star-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await this.toggleStar(parseInt(btn.dataset.id));
            });
        });

        // Edit handlers
        container.querySelectorAll('.vault-edit-record').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showEditForm(parseInt(btn.dataset.id));
            });
        });

        // Delete handlers
        container.querySelectorAll('.vault-delete-record').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await this.deleteRecord(parseInt(btn.dataset.id));
            });
        });
    },

    /**
     * Show the add record form
     */
    showAddRecordForm() {
        const container = document.getElementById('vault-record-list');
        const existing = document.getElementById('vault-add-record-form');
        if (existing) {
            existing.remove();
            return;
        }

        const form = document.createElement('div');
        form.id = 'vault-add-record-form';
        form.className = 'vault-add-record-form';
        form.innerHTML = `
            <div class="vault-form-row">
                <select id="vault-record-type">
                    <option value="text">Text</option>
                    <option value="document">Document (PDF)</option>
                    <option value="image">Image</option>
                </select>
                <input type="date" id="vault-record-date" value="${new Date().toISOString().split('T')[0]}" required>
            </div>
            <input type="text" id="vault-record-title" placeholder="Record title">
            <textarea id="vault-record-content" placeholder="Record content (for text records)" rows="4"></textarea>
            <div class="vault-file-upload hidden" id="vault-file-upload">
                <div class="vault-dropzone" id="vault-record-dropzone">
                    <p>Drag & drop a file here or click to browse</p>
                    <input type="file" id="vault-record-file" class="hidden">
                </div>
                <div class="vault-file-name hidden" id="vault-file-name"></div>
            </div>
            <div class="vault-form-actions">
                <button class="vault-btn vault-btn-secondary" id="vault-record-cancel">Cancel</button>
                <button class="vault-btn vault-btn-primary" id="vault-record-submit">Add Record</button>
            </div>
        `;

        container.insertBefore(form, container.firstChild);

        const typeSelect = document.getElementById('vault-record-type');
        const fileUpload = document.getElementById('vault-file-upload');
        const contentArea = document.getElementById('vault-record-content');
        const dropzone = document.getElementById('vault-record-dropzone');
        const fileInput = document.getElementById('vault-record-file');

        typeSelect.addEventListener('change', () => {
            const isFile = typeSelect.value !== 'text';
            fileUpload.classList.toggle('hidden', !isFile);
            contentArea.classList.toggle('hidden', isFile);
            if (typeSelect.value === 'document') {
                fileInput.accept = '.pdf,.doc,.docx,.txt';
            } else if (typeSelect.value === 'image') {
                fileInput.accept = 'image/*';
            }
        });

        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                this.showSelectedFile(e.dataTransfer.files[0].name);
            }
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                this.showSelectedFile(fileInput.files[0].name);
            }
        });

        document.getElementById('vault-record-cancel').addEventListener('click', () => form.remove());
        document.getElementById('vault-record-submit').addEventListener('click', () => this.submitRecord());
        document.getElementById('vault-record-title').focus();
    },

    showSelectedFile(name) {
        const el = document.getElementById('vault-file-name');
        el.textContent = name;
        el.classList.remove('hidden');
    },

    async submitRecord() {
        const type = document.getElementById('vault-record-type').value;
        const title = document.getElementById('vault-record-title').value.trim();
        const date = document.getElementById('vault-record-date').value;
        const content = document.getElementById('vault-record-content').value.trim();
        const fileInput = document.getElementById('vault-record-file');

        if (!date) {
            alert('Date is required.');
            return;
        }

        const formData = new FormData();
        formData.append('record_type', type);
        formData.append('title', title);
        formData.append('record_date', date);

        if (type === 'text') {
            formData.append('content', content);
        } else {
            if (!fileInput.files.length) {
                alert('Please select a file.');
                return;
            }
            formData.append('file', fileInput.files[0]);
        }

        try {
            const submitBtn = document.getElementById('vault-record-submit');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Adding...';

            await api.addVaultRecord(this.currentCase.id, formData);

            // Reload case to get updated records
            const caseData = await api.getVaultCase(this.currentCase.id);
            this.currentCase = caseData;
            this.currentUserId = caseData.current_user_id;

            const form = document.getElementById('vault-add-record-form');
            if (form) form.remove();

            this.renderRecordList();
        } catch (error) {
            alert('Failed to add record: ' + error.message);
            const submitBtn = document.getElementById('vault-record-submit');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Add Record';
            }
        }
    },

    async toggleStar(recordId) {
        try {
            const updated = await api.toggleVaultRecordStar(recordId);
            // Update local state
            const record = this.currentCase.records.find(r => r.id === recordId);
            if (record) {
                record.starred = updated.starred;
            }
            this.renderRecordList();
        } catch (error) {
            console.error('Failed to toggle star:', error);
        }
    },

    async deleteRecord(recordId) {
        if (!confirm('Delete this record? This cannot be undone.')) return;
        try {
            await api.deleteVaultRecord(recordId);
            this.currentCase.records = this.currentCase.records.filter(r => r.id !== recordId);
            this.showCaseDetail();
        } catch (error) {
            alert('Failed to delete record: ' + error.message);
        }
    },

    isEditableRecord(record) {
        if (record.record_type !== 'text') return false;
        if (record.created_by_user_id !== this.currentUserId) return false;
        const created = new Date(record.created_at);
        const now = new Date();
        const hoursDiff = (now - created) / (1000 * 60 * 60);
        return hoursDiff <= 24;
    },

    showEditForm(recordId) {
        const record = this.currentCase.records.find(r => r.id === recordId);
        if (!record) return;

        const recordEl = document.querySelector(`.vault-record-item[data-id="${recordId}"]`);
        if (!recordEl) return;

        const infoEl = recordEl.querySelector('.vault-record-info');
        const actionsEl = recordEl.querySelector('.vault-record-actions');

        infoEl.innerHTML = `
            <input type="text" class="vault-edit-title" value="${this.escapeHtml(record.title || '')}" placeholder="Record title">
            <textarea class="vault-edit-content" rows="4" placeholder="Record content">${this.escapeHtml(record.content || '')}</textarea>
            <div class="vault-form-actions">
                <button class="vault-btn vault-btn-secondary vault-edit-cancel">Cancel</button>
                <button class="vault-btn vault-btn-primary vault-edit-save">Save</button>
            </div>
        `;
        actionsEl.classList.add('hidden');

        infoEl.querySelector('.vault-edit-cancel').addEventListener('click', () => this.renderRecordList());
        infoEl.querySelector('.vault-edit-save').addEventListener('click', async () => {
            const title = infoEl.querySelector('.vault-edit-title').value.trim();
            const content = infoEl.querySelector('.vault-edit-content').value.trim();
            try {
                const updated = await api.updateVaultRecord(recordId, { title, content });
                const idx = this.currentCase.records.findIndex(r => r.id === recordId);
                if (idx !== -1) {
                    this.currentCase.records[idx] = updated;
                }
                this.renderRecordList();
            } catch (error) {
                alert('Failed to update record: ' + error.message);
            }
        });

        infoEl.querySelector('.vault-edit-title').focus();
    },

    // Utility methods
    getTypeIcon(type) {
        switch (type) {
            case 'text': return '&#128196;';
            case 'document': return '&#128209;';
            case 'image': return '&#128247;';
            default: return '&#128196;';
        }
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        const y = d.getFullYear();
        const m = d.getMonth() + 1;
        const day = d.getDate();
        const pad = (n) => String(n).padStart(2, '0');
        const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        switch (this.dateFormat) {
            case 'DD/MM/YYYY': return `${pad(day)}/${pad(m)}/${y}`;
            case 'MM/DD/YYYY': return `${pad(m)}/${pad(day)}/${y}`;
            case 'DD.MM.YYYY': return `${pad(day)}.${pad(m)}.${y}`;
            case 'D MMM YYYY': return `${day} ${monthNames[m - 1]} ${y}`;
            default: return `${y}-${pad(m)}-${pad(day)}`;
        }
    },

    formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
