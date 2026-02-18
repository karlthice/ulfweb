/**
 * Chat functionality
 */

const chat = {
    conversationId: null,
    messages: [],
    isStreaming: false,
    servers: [],
    attachedPdfText: null,
    attachedPdfName: null,
    attachedImageBase64: null,
    attachedImageName: null,
    MAX_PDF_SIZE: 10 * 1024 * 1024, // 10MB
    MAX_IMAGE_SIZE: 20 * 1024 * 1024, // 20MB
    MAX_TEXT_LENGTH: 50000, // Max characters to include

    /**
     * Initialize chat functionality
     */
    init() {
        this.setupEventListeners();
        this.setupAutoResize();
        this.setupMarked();
        this.setupServerSelector();
        this.setupAttachment();
        this.setupImageAttachment();
        this.loadServers();
    },

    /**
     * Load available servers from database
     */
    async loadServers() {
        const serverSelect = document.getElementById('chat-model');

        try {
            this.servers = await api.getActiveServers();

            // Clear existing options
            serverSelect.innerHTML = '';

            if (this.servers.length === 0) {
                serverSelect.innerHTML = '<option value="">No servers configured</option>';
                return;
            }

            // Add server options
            for (const server of this.servers) {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.friendly_name;
                serverSelect.appendChild(option);
            }

            // Load current setting and set selected server
            const settings = await api.getSettings();
            if (settings && settings.model && this.servers.some(s => s.id.toString() === settings.model)) {
                serverSelect.value = settings.model;
            }
        } catch (error) {
            console.error('Failed to load servers:', error);
            serverSelect.innerHTML = '<option value="">Failed to load servers</option>';
        }
    },

    /**
     * Setup server selector change handler
     */
    setupServerSelector() {
        const serverSelect = document.getElementById('chat-model');

        serverSelect.addEventListener('change', async () => {
            try {
                await api.updateSettings({ model: serverSelect.value });
                // Notify user to start a new chat when server changes
                if (this.conversationId && this.messages.length > 0) {
                    this.showServerChangeNotice();
                }
            } catch (error) {
                console.error('Failed to save server setting:', error);
            }
        });
    },

    /**
     * Show notice that user should start a new chat after server change
     */
    showServerChangeNotice() {
        // Remove existing notice if present
        const existingNotice = document.querySelector('.server-change-notice');
        if (existingNotice) {
            existingNotice.remove();
        }

        const notice = document.createElement('div');
        notice.className = 'server-change-notice';
        notice.innerHTML = `
            <span>Server changed. Start a new chat for best results.</span>
            <button class="notice-btn" onclick="document.getElementById('new-chat-btn').click(); this.parentElement.remove();">New Chat</button>
            <button class="notice-close" onclick="this.parentElement.remove();">&times;</button>
        `;

        const inputArea = document.getElementById('input-area');
        inputArea.insertBefore(notice, inputArea.firstChild);
    },

    /**
     * Setup attachment menu and handlers
     */
    setupAttachment() {
        const attachBtn = document.getElementById('attach-btn');
        const attachMenu = document.getElementById('attach-menu');
        const attachPdf = document.getElementById('attach-pdf');
        const attachImage = document.getElementById('attach-image');
        const pdfInput = document.getElementById('pdf-input');
        const removeBtn = document.getElementById('attachment-remove');

        // Toggle menu on button click
        attachBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            attachMenu.classList.toggle('hidden');
        });

        // Close menu when clicking outside
        document.addEventListener('click', () => {
            attachMenu.classList.add('hidden');
        });

        // PDF option
        attachPdf.addEventListener('click', () => {
            attachMenu.classList.add('hidden');
            pdfInput.click();
        });

        // Image option
        attachImage.addEventListener('click', () => {
            attachMenu.classList.add('hidden');
            document.getElementById('image-input').click();
        });

        // PDF file change handler
        pdfInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Check file size
            if (file.size > this.MAX_PDF_SIZE) {
                alert(`PDF file is too large. Maximum size is ${this.MAX_PDF_SIZE / 1024 / 1024}MB.`);
                pdfInput.value = '';
                return;
            }

            try {
                attachBtn.disabled = true;
                attachBtn.innerHTML = '<span class="icon">⏳</span>';

                const text = await this.extractPdfText(file);

                if (text.length === 0) {
                    alert('Could not extract text from PDF. The file may be image-based or protected.');
                    pdfInput.value = '';
                    return;
                }

                if (text.length > this.MAX_TEXT_LENGTH) {
                    const truncated = text.substring(0, this.MAX_TEXT_LENGTH);
                    this.attachedPdfText = truncated;
                    alert(`PDF text was truncated to ${this.MAX_TEXT_LENGTH} characters due to size limits.`);
                } else {
                    this.attachedPdfText = text;
                }

                this.attachedPdfName = file.name;
                this.showAttachmentIndicator(file.name);

            } catch (error) {
                console.error('Failed to extract PDF text:', error);
                alert('Failed to read PDF file. Please try another file.');
                pdfInput.value = '';
            } finally {
                attachBtn.disabled = false;
                attachBtn.innerHTML = '<span class="icon">📎</span>';
            }
        });

        removeBtn.addEventListener('click', () => {
            this.clearAttachment();
        });

        // Setup clipboard paste for images
        this.setupClipboardPaste();
    },

    /**
     * Setup clipboard paste handler for images
     */
    setupClipboardPaste() {
        document.addEventListener('paste', async (e) => {
            // Only handle paste when message input is focused or chat area is active
            const activeElement = document.activeElement;
            const messageInput = document.getElementById('message-input');
            const chatPanel = document.getElementById('chat-panel');

            if (!chatPanel.contains(activeElement) && activeElement !== messageInput) {
                return;
            }

            const items = e.clipboardData?.items;
            if (!items) return;

            for (const item of items) {
                if (item.type.startsWith('image/')) {
                    e.preventDefault();
                    const file = item.getAsFile();
                    if (file) {
                        await this.handleImageFile(file);
                    }
                    break;
                }
            }
        });
    },

    /**
     * Handle image file (from input or paste)
     */
    async handleImageFile(file) {
        // Check file size
        if (file.size > this.MAX_IMAGE_SIZE) {
            alert(`Image is too large. Maximum size is ${this.MAX_IMAGE_SIZE / 1024 / 1024}MB.`);
            return;
        }

        try {
            // Convert to base64
            const base64 = await this.fileToBase64(file);
            this.attachedImageBase64 = base64;
            this.attachedImageName = file.name || 'pasted-image.png';

            // Show preview
            const imagePreview = document.getElementById('image-preview');
            imagePreview.src = base64;
            imagePreview.classList.remove('hidden');

        } catch (error) {
            console.error('Failed to load image:', error);
            alert('Failed to load image. Please try another file.');
        }
    },

    /**
     * Extract text from PDF file using pdf.js
     */
    async extractPdfText(file) {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

        let fullText = '';

        for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const textContent = await page.getTextContent();

            const pageText = textContent.items
                .map(item => item.str)
                .join(' ');

            fullText += pageText + '\n\n';
        }

        return fullText.trim();
    },

    /**
     * Show attachment indicator
     */
    showAttachmentIndicator(filename) {
        const indicator = document.getElementById('attachment-indicator');
        const nameSpan = document.getElementById('attachment-name');

        nameSpan.textContent = filename;
        indicator.classList.remove('hidden');
    },

    /**
     * Clear attachment
     */
    clearAttachment() {
        this.attachedPdfText = null;
        this.attachedPdfName = null;

        document.getElementById('pdf-input').value = '';
        document.getElementById('attachment-indicator').classList.add('hidden');
    },

    /**
     * Setup image attachment handlers
     */
    setupImageAttachment() {
        const imageInput = document.getElementById('image-input');

        imageInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (file) {
                await this.handleImageFile(file);
            }
        });

        // Click preview to remove
        document.getElementById('image-preview').addEventListener('click', () => {
            this.clearImageAttachment();
        });
    },

    /**
     * Convert file to base64
     */
    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    },

    /**
     * Clear image attachment
     */
    clearImageAttachment() {
        this.attachedImageBase64 = null;
        this.attachedImageName = null;

        document.getElementById('image-input').value = '';
        document.getElementById('image-preview').classList.add('hidden');
    },

    /**
     * Configure marked for markdown rendering
     */
    setupMarked() {
        marked.setOptions({
            breaks: true,
            gfm: true
        });
    },

    /**
     * Render markdown to HTML safely
     */
    renderMarkdown(text) {
        return marked.parse(text);
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const input = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const stopBtn = document.getElementById('stop-btn');

        // Send message on button click
        sendBtn.addEventListener('click', () => this.sendMessage());

        // Stop generation
        stopBtn.addEventListener('click', () => this.stopGeneration());

        // Send on Enter (but not Shift+Enter)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    },

    /**
     * Setup auto-resizing textarea
     */
    setupAutoResize() {
        const input = document.getElementById('message-input');

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 200) + 'px';
        });
    },

    /**
     * Load a conversation
     */
    async loadConversation(id) {
        try {
            const conv = await api.getConversation(id);
            if (!conv) {
                this.clear();
                return;
            }

            this.conversationId = id;
            this.messages = conv.messages;

            // Update UI
            document.getElementById('chat-title').textContent = conv.title;
            const emptyState = document.getElementById('empty-state');
            if (emptyState) {
                emptyState.classList.add('hidden');
            }
            document.getElementById('message-input').disabled = false;
            document.getElementById('send-btn').disabled = false;

            this.renderMessages();
        } catch (error) {
            console.error('Failed to load conversation:', error);
        }
    },

    /**
     * Clear the chat area
     */
    clear() {
        this.conversationId = null;
        this.messages = [];

        document.getElementById('chat-title').textContent = 'Select a conversation';
        document.getElementById('empty-state').classList.remove('hidden');
        document.getElementById('message-input').disabled = true;
        document.getElementById('send-btn').disabled = true;

        const container = document.getElementById('messages');
        container.innerHTML = '<div class="empty-state" id="empty-state"><p>Start a new conversation or select one from the sidebar</p></div>';
    },

    /**
     * Render all messages
     */
    renderMessages() {
        const container = document.getElementById('messages');
        container.innerHTML = '';

        for (const msg of this.messages) {
            this.appendMessage(msg.role, msg.content, false);
        }

        this.scrollToBottom();
    },

    /**
     * Append a message to the chat
     */
    appendMessage(role, content, scroll = true) {
        const container = document.getElementById('messages');

        // Remove empty state if present
        const emptyState = document.getElementById('empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

        const innerDiv = document.createElement('div');
        innerDiv.className = 'message-inner';

        const roleDiv = document.createElement('div');
        roleDiv.className = 'message-role';
        roleDiv.textContent = role === 'user' ? 'You' : 'AI';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        if (role === 'assistant' && content) {
            contentDiv.innerHTML = this.renderMarkdown(content);
        } else {
            contentDiv.textContent = content;
        }

        innerDiv.appendChild(roleDiv);
        innerDiv.appendChild(contentDiv);

        // Add speak button for assistant messages
        if (role === 'assistant' && content) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            const speakBtn = tts.createSpeakButton(() => tts.htmlToText(contentDiv.innerHTML));
            actionsDiv.appendChild(speakBtn);
            innerDiv.appendChild(actionsDiv);
        }

        msgDiv.appendChild(innerDiv);

        container.appendChild(msgDiv);

        if (scroll) {
            this.scrollToBottom();
        }

        return msgDiv;
    },

    /**
     * Send a message
     */
    async sendMessage() {
        const input = document.getElementById('message-input');
        const content = input.value.trim();

        if (!content || !this.conversationId || this.isStreaming) {
            return;
        }

        // Clear input
        input.value = '';
        input.style.height = 'auto';

        // Build the full message with attachments if present
        let displayContent = content;
        let sendContent = content;
        let imageBase64 = null;

        if (this.attachedPdfText) {
            displayContent = `📎 ${this.attachedPdfName}\n\n${content}`;
            sendContent = `[Attached PDF: ${this.attachedPdfName}]\n\nDocument content:\n${this.attachedPdfText}\n\n---\n\nUser question: ${content}`;
            this.clearAttachment();
        }

        if (this.attachedImageBase64) {
            displayContent = `🖼️ ${this.attachedImageName}\n\n${content}`;
            imageBase64 = this.attachedImageBase64;
            this.clearImageAttachment();
        }

        // Add user message to UI (with image preview if applicable)
        const msgDiv = this.appendMessage('user', displayContent);
        if (imageBase64) {
            const img = document.createElement('img');
            img.src = imageBase64;
            img.style.maxWidth = '200px';
            img.style.maxHeight = '150px';
            img.style.borderRadius = '8px';
            img.style.marginTop = '0.5rem';
            msgDiv.querySelector('.message-content').appendChild(img);
        }
        this.messages.push({ role: 'user', content: displayContent });

        // Start streaming
        this.startStreaming();

        // Create assistant message placeholder
        const assistantDiv = this.appendMessage('assistant', '');
        assistantDiv.classList.add('streaming');
        const contentDiv = assistantDiv.querySelector('.message-content');

        let assistantContent = '';
        let tokenCount = 0;
        const startTime = performance.now();
        const tokensCounter = document.getElementById('tokens-counter');
        let renderPending = false;

        await sseHandler.streamMessage(
            this.conversationId,
            sendContent,
            // onChunk
            (chunk) => {
                assistantContent += chunk;
                if (!renderPending) {
                    renderPending = true;
                    requestAnimationFrame(() => {
                        renderPending = false;
                        contentDiv.innerHTML = this.renderMarkdown(assistantContent);
                        this.scrollToBottom();
                    });
                }

                // Update tokens/sec counter (approximate tokens by splitting on whitespace/punctuation)
                tokenCount++;
                const elapsed = (performance.now() - startTime) / 1000;
                if (elapsed > 0) {
                    const tokensPerSec = (tokenCount / elapsed).toFixed(1);
                    tokensCounter.textContent = `${tokensPerSec} tok/s`;
                }
            },
            // onDone
            (messageId) => {
                renderPending = false;
                assistantDiv.classList.remove('streaming');
                if (assistantContent) {
                    // Render final markdown
                    contentDiv.innerHTML = this.renderMarkdown(assistantContent);
                    this.messages.push({ role: 'assistant', content: assistantContent });

                    // Add speak button after streaming completes
                    const innerDiv = assistantDiv.querySelector('.message-inner');
                    if (innerDiv && !innerDiv.querySelector('.message-actions')) {
                        const actionsDiv = document.createElement('div');
                        actionsDiv.className = 'message-actions';
                        const speakBtn = tts.createSpeakButton(() => tts.htmlToText(contentDiv.innerHTML));
                        actionsDiv.appendChild(speakBtn);
                        innerDiv.appendChild(actionsDiv);
                    }
                }

                // Show final tokens/sec
                const elapsed = (performance.now() - startTime) / 1000;
                if (elapsed > 0 && tokenCount > 0) {
                    const tokensPerSec = (tokenCount / elapsed).toFixed(1);
                    tokensCounter.textContent = `${tokensPerSec} tok/s`;
                }

                this.stopStreaming();

                // Refresh conversation list to get updated title
                conversations.refresh();
            },
            // onError
            (error) => {
                assistantDiv.classList.remove('streaming');
                assistantDiv.classList.add('error');
                contentDiv.textContent = `Error: ${error}`;
                tokensCounter.textContent = '';
                this.stopStreaming();
            },
            imageBase64
        );
    },

    /**
     * Stop the current generation
     */
    stopGeneration() {
        sseHandler.abort();
    },

    /**
     * Start streaming state
     */
    startStreaming() {
        this.isStreaming = true;
        document.getElementById('send-btn').classList.add('hidden');
        document.getElementById('stop-btn').classList.remove('hidden');
        document.getElementById('message-input').disabled = true;
    },

    /**
     * Stop streaming state
     */
    stopStreaming() {
        this.isStreaming = false;
        document.getElementById('send-btn').classList.remove('hidden');
        document.getElementById('stop-btn').classList.add('hidden');
        document.getElementById('message-input').disabled = false;
        document.getElementById('message-input').focus();
    },

    /**
     * Scroll to the bottom of the messages
     */
    scrollToBottom() {
        const container = document.getElementById('messages');
        container.scrollTop = container.scrollHeight;
    }
};
