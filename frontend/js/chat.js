/**
 * Chat functionality
 */

const chat = {
    conversationId: null,
    messages: [],
    isStreaming: false,

    /**
     * Initialize chat functionality
     */
    init() {
        this.setupEventListeners();
        this.setupAutoResize();
        this.setupMarked();
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
            document.getElementById('empty-state').classList.add('hidden');
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

        // Add user message to UI
        this.appendMessage('user', content);
        this.messages.push({ role: 'user', content });

        // Start streaming
        this.startStreaming();

        // Create assistant message placeholder
        const assistantDiv = this.appendMessage('assistant', '');
        assistantDiv.classList.add('streaming');
        const contentDiv = assistantDiv.querySelector('.message-content');

        let assistantContent = '';

        await sseHandler.streamMessage(
            this.conversationId,
            content,
            // onChunk
            (chunk) => {
                assistantContent += chunk;
                contentDiv.textContent = assistantContent;
                this.scrollToBottom();
            },
            // onDone
            (messageId) => {
                assistantDiv.classList.remove('streaming');
                if (assistantContent) {
                    // Render final markdown
                    contentDiv.innerHTML = this.renderMarkdown(assistantContent);
                    this.messages.push({ role: 'assistant', content: assistantContent });
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
                this.stopStreaming();
            }
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
