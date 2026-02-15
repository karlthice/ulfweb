/**
 * Documents module for GraphRAG document search
 */

const documents = (function() {
    const API_BASE = '/api/v1/documents';

    // DOM elements
    let collectionSelect;
    let uploadBtn;
    let documentsToggle;
    let documentsList;
    let docCount;
    let queryInput;
    let searchBtn;
    let queryStopBtn;
    let queryResults;
    let uploadModal;
    let uploadDropzone;
    let uploadFileInput;
    let uploadProgress;
    let progressFilename;
    let progressFill;
    let progressStatus;

    // State
    let collections = [];
    let currentDocuments = [];
    let abortController = null;
    let pollIntervals = {};

    /**
     * Initialize the documents module
     */
    function init() {
        // Get DOM elements
        collectionSelect = document.getElementById('collection-select');
        uploadBtn = document.getElementById('upload-btn');
        documentsToggle = document.getElementById('documents-toggle');
        documentsList = document.getElementById('documents-list');
        docCount = document.getElementById('doc-count');
        queryInput = document.getElementById('query-input');
        searchBtn = document.getElementById('search-btn');
        queryStopBtn = document.getElementById('query-stop-btn');
        queryResults = document.getElementById('query-results');
        uploadModal = document.getElementById('upload-modal');
        uploadDropzone = document.getElementById('upload-dropzone');
        uploadFileInput = document.getElementById('upload-file-input');
        uploadProgress = document.getElementById('upload-progress');
        progressFilename = document.getElementById('progress-filename');
        progressFill = document.getElementById('progress-fill');
        progressStatus = document.getElementById('progress-status');

        setupEventListeners();
        loadCollections();

        console.log('Documents module initialized');
    }

    /**
     * Setup event listeners
     */
    function setupEventListeners() {
        // Collection selector
        collectionSelect.addEventListener('change', () => {
            loadDocuments(collectionSelect.value);
        });

        // Upload button
        uploadBtn.addEventListener('click', openUploadModal);

        // Documents toggle
        documentsToggle.addEventListener('click', toggleDocumentsList);

        // Search button
        searchBtn.addEventListener('click', performQuery);

        // Stop button
        queryStopBtn.addEventListener('click', stopQuery);

        // Enter to search
        queryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                performQuery();
            }
        });

        // Upload modal handlers
        document.getElementById('close-upload-modal').addEventListener('click', closeUploadModal);
        document.getElementById('upload-modal-overlay').addEventListener('click', closeUploadModal);
        document.getElementById('browse-btn').addEventListener('click', () => uploadFileInput.click());
        uploadFileInput.addEventListener('change', handleFileSelect);

        // Drag and drop
        uploadDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadDropzone.classList.add('dragover');
        });
        uploadDropzone.addEventListener('dragleave', () => {
            uploadDropzone.classList.remove('dragover');
        });
        uploadDropzone.addEventListener('drop', handleFileDrop);

        // Close modal on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeUploadModal();
            }
        });
    }

    /**
     * Load collections from API
     */
    async function loadCollections() {
        try {
            const response = await fetch(`${API_BASE}/collections`);
            if (!response.ok) throw new Error('Failed to fetch collections');
            collections = await response.json();
            renderCollectionDropdown();

            if (collections.length > 0) {
                collectionSelect.value = collections[0].id;
                loadDocuments(collections[0].id);
            }
        } catch (error) {
            console.error('Failed to load collections:', error);
            collectionSelect.innerHTML = '<option value="">Error loading collections</option>';
        }
    }

    /**
     * Render collection dropdown
     */
    function renderCollectionDropdown() {
        collectionSelect.innerHTML = collections.map(c =>
            `<option value="${c.id}">${escapeHtml(c.name)} (${c.document_count} docs)</option>`
        ).join('');
    }

    /**
     * Load documents for a collection
     */
    async function loadDocuments(collectionId) {
        if (!collectionId) return;

        try {
            const response = await fetch(`${API_BASE}/collections/${collectionId}/documents`);
            if (!response.ok) throw new Error('Failed to fetch documents');
            currentDocuments = await response.json();
            renderDocumentsList();

            // Start polling for pending documents
            currentDocuments.forEach(doc => {
                if (doc.status === 'pending' || doc.status === 'processing') {
                    startPollingStatus(doc.id);
                }
            });
        } catch (error) {
            console.error('Failed to load documents:', error);
            documentsList.innerHTML = '<div class="error">Failed to load documents</div>';
        }
    }

    /**
     * Render documents list
     */
    function renderDocumentsList() {
        docCount.textContent = currentDocuments.length;

        if (currentDocuments.length === 0) {
            documentsList.innerHTML = '<div class="empty-docs">No documents uploaded yet</div>';
            return;
        }

        documentsList.innerHTML = currentDocuments.map(doc => `
            <div class="document-item" data-id="${doc.id}">
                <div class="doc-icon">${getStatusIcon(doc.status)}</div>
                <div class="doc-info ${doc.status === 'ready' ? 'clickable' : ''}"
                     ${doc.status === 'ready' ? `onclick="documents.openDocument(${doc.id})"` : ''}
                     title="${doc.status === 'ready' ? 'Click to open PDF' : ''}">
                    <div class="doc-name">${escapeHtml(doc.original_filename)}</div>
                    <div class="doc-meta">
                        ${doc.page_count ? `${doc.page_count} pages` : ''}
                        ${formatFileSize(doc.file_size)}
                        - ${getStatusText(doc.status)}
                        ${doc.error_message ? `<span class="doc-error" title="${escapeHtml(doc.error_message)}">!</span>` : ''}
                    </div>
                </div>
                <button class="doc-delete" onclick="event.stopPropagation(); documents.deleteDocument(${doc.id})" title="Delete">
                    &times;
                </button>
            </div>
        `).join('');
    }

    /**
     * Get status icon
     */
    function getStatusIcon(status) {
        switch (status) {
            case 'ready': return '&#10003;';
            case 'processing': return '&#8635;';
            case 'pending': return '&#8987;';
            case 'error': return '&#10007;';
            default: return '?';
        }
    }

    /**
     * Get status text
     */
    function getStatusText(status) {
        switch (status) {
            case 'ready': return 'Ready';
            case 'processing': return 'Processing...';
            case 'pending': return 'Pending...';
            case 'error': return 'Error';
            default: return status;
        }
    }

    /**
     * Toggle documents list visibility
     */
    function toggleDocumentsList() {
        documentsList.classList.toggle('hidden');
        const icon = documentsToggle.querySelector('.icon');
        icon.innerHTML = documentsList.classList.contains('hidden') ? '&#9660;' : '&#9650;';
    }

    /**
     * Open upload modal
     */
    function openUploadModal() {
        uploadModal.classList.remove('hidden');
        uploadProgress.classList.add('hidden');
        uploadDropzone.classList.remove('hidden');
        uploadFileInput.value = '';
    }

    /**
     * Close upload modal
     */
    function closeUploadModal() {
        uploadModal.classList.add('hidden');
    }

    /**
     * Handle file selection
     */
    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) uploadFile(file);
    }

    /**
     * Handle file drop
     */
    function handleFileDrop(e) {
        e.preventDefault();
        uploadDropzone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) uploadFile(file);
    }

    /**
     * Upload a file
     */
    async function uploadFile(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('Please select a PDF file');
            return;
        }

        const collectionId = collectionSelect.value;
        if (!collectionId) {
            alert('Please select a collection first');
            return;
        }

        uploadDropzone.classList.add('hidden');
        uploadProgress.classList.remove('hidden');
        progressFilename.textContent = file.name;
        progressFill.style.width = '0%';
        progressStatus.textContent = 'Uploading...';

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${API_BASE}/collections/${collectionId}/documents`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const doc = await response.json();
            progressFill.style.width = '100%';
            progressStatus.textContent = 'Processing...';

            // Start polling for status
            startPollingStatus(doc.id);

            // Reload documents list
            await loadDocuments(collectionId);

            // Close modal after a short delay
            setTimeout(closeUploadModal, 1500);

        } catch (error) {
            progressStatus.textContent = `Error: ${error.message}`;
            progressFill.style.backgroundColor = 'var(--error)';
        }
    }

    /**
     * Start polling document status
     */
    function startPollingStatus(documentId) {
        if (pollIntervals[documentId]) return;

        pollIntervals[documentId] = setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE}/documents/${documentId}/status`);
                if (!response.ok) {
                    stopPollingStatus(documentId);
                    return;
                }

                const status = await response.json();

                if (status.status === 'ready' || status.status === 'error') {
                    stopPollingStatus(documentId);
                    // Reload documents to update UI
                    loadDocuments(collectionSelect.value);
                    // Update collection dropdown to reflect new doc count
                    loadCollections();
                }
            } catch (error) {
                console.error('Status poll error:', error);
                stopPollingStatus(documentId);
            }
        }, 2000);
    }

    /**
     * Stop polling document status
     */
    function stopPollingStatus(documentId) {
        if (pollIntervals[documentId]) {
            clearInterval(pollIntervals[documentId]);
            delete pollIntervals[documentId];
        }
    }

    /**
     * Delete a document
     */
    async function deleteDocument(documentId) {
        if (!confirm('Delete this document?')) return;

        try {
            const response = await fetch(`${API_BASE}/documents/${documentId}`, {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error('Failed to delete document');

            stopPollingStatus(documentId);
            await loadDocuments(collectionSelect.value);
            loadCollections();
        } catch (error) {
            console.error('Failed to delete document:', error);
            alert('Failed to delete document');
        }
    }

    /**
     * Open a document PDF in a new window
     */
    function openDocument(documentId) {
        window.open(`${API_BASE}/documents/${documentId}/file`, '_blank');
    }

    /**
     * Perform GraphRAG query
     */
    async function performQuery() {
        const question = queryInput.value.trim();
        if (!question) return;

        const collectionId = collectionSelect.value;
        if (!collectionId) {
            alert('Please select a collection first');
            return;
        }

        // Abort any existing query
        stopQuery();

        // Create new abort controller
        abortController = new AbortController();

        // Update UI
        searchBtn.classList.add('hidden');
        queryStopBtn.classList.remove('hidden');
        queryResults.innerHTML = '<div class="result-answer streaming"></div>';

        const answerDiv = queryResults.querySelector('.result-answer');
        let fullAnswer = '';
        let sources = [];

        try {
            const response = await fetch(`${API_BASE}/collections/${collectionId}/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question }),
                signal: abortController.signal
            });

            if (!response.ok) throw new Error(`HTTP error: ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();

                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process complete SSE messages
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        try {
                            const parsed = JSON.parse(data);

                            if (parsed.type === 'content') {
                                fullAnswer += parsed.content;
                                answerDiv.innerHTML = marked.parse(fullAnswer);
                            } else if (parsed.type === 'sources') {
                                sources = parsed.sources || [];
                            } else if (parsed.type === 'error') {
                                answerDiv.innerHTML = `<span class="error">Error: ${escapeHtml(parsed.content)}</span>`;
                            }
                        } catch (e) {
                            // Skip invalid JSON
                        }
                    }
                }
            }

            // Render final result with sources
            answerDiv.classList.remove('streaming');
            if (sources.length > 0) {
                const sourcesHtml = `
                    <div class="result-sources">
                        <strong>Sources:</strong> ${sources.map(s => escapeHtml(s)).join(', ')}
                    </div>
                `;
                queryResults.innerHTML = `
                    <div class="result-answer">${marked.parse(fullAnswer)}</div>
                    ${sourcesHtml}
                `;
            }

            // Add speak button after query completes
            if (fullAnswer) {
                const resultAnswer = queryResults.querySelector('.result-answer');
                if (resultAnswer) {
                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'result-actions';
                    const speakBtn = tts.createSpeakButton(() => tts.htmlToText(resultAnswer.innerHTML));
                    actionsDiv.appendChild(speakBtn);
                    resultAnswer.after(actionsDiv);
                }
            }

        } catch (error) {
            if (error.name === 'AbortError') {
                // Query was intentionally stopped
            } else {
                answerDiv.innerHTML = `<span class="error">Error: ${escapeHtml(error.message)}</span>`;
            }
        } finally {
            searchBtn.classList.remove('hidden');
            queryStopBtn.classList.add('hidden');
            abortController = null;
        }
    }

    /**
     * Stop the current query
     */
    function stopQuery() {
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }

    /**
     * Format file size
     */
    function formatFileSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    return {
        init,
        loadCollections,
        loadDocuments,
        deleteDocument,
        openDocument,
        performQuery,
        stopQuery
    };
})();
