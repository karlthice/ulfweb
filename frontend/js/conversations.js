/**
 * Conversation list management
 */

const conversations = {
    list: [],
    currentId: null,

    /**
     * Initialize the conversation list
     */
    async init() {
        await this.refresh();
        this.setupEventListeners();

        // Auto-select the most recent conversation if one exists
        if (this.list.length > 0) {
            await this.select(this.list[0].id);
        }
    },

    /**
     * Refresh the conversation list from the server
     */
    async refresh() {
        try {
            this.list = await api.listConversations();
            this.render();
        } catch (error) {
            console.error('Failed to load conversations:', error);
        }
    },

    /**
     * Render the conversation list
     */
    render() {
        const container = document.getElementById('conversations-list');
        container.innerHTML = '';

        if (this.list.length === 0) {
            container.innerHTML = '<p style="padding: 1rem; color: var(--text-muted); text-align: center;">No conversations yet</p>';
            return;
        }

        for (const conv of this.list) {
            const item = document.createElement('div');
            item.className = 'conversation-item' + (conv.id === this.currentId ? ' active' : '');
            item.dataset.id = conv.id;
            item.innerHTML = `
                <span class="conversation-title">${this.escapeHtml(conv.title)}</span>
                <button class="conversation-delete" title="Delete conversation">&times;</button>
            `;
            container.appendChild(item);
        }
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const container = document.getElementById('conversations-list');

        container.addEventListener('click', async (e) => {
            const item = e.target.closest('.conversation-item');
            if (!item) return;

            const id = parseInt(item.dataset.id);

            // Handle delete button
            if (e.target.classList.contains('conversation-delete')) {
                e.stopPropagation();
                await this.delete(id);
                return;
            }

            // Select conversation
            await this.select(id);
        });

        // New chat button
        document.getElementById('new-chat-btn').addEventListener('click', async () => {
            await this.create();
        });
    },

    /**
     * Create a new conversation
     */
    async create() {
        try {
            const conv = await api.createConversation();
            this.list.unshift(conv);
            await this.select(conv.id);
            this.render();

            // Close sidebar on mobile
            this.closeSidebarOnMobile();
        } catch (error) {
            console.error('Failed to create conversation:', error);
        }
    },

    /**
     * Select a conversation
     */
    async select(id) {
        this.currentId = id;
        this.render();
        await chat.loadConversation(id);

        // Close sidebar on mobile
        this.closeSidebarOnMobile();
    },

    /**
     * Delete a conversation
     */
    async delete(id) {
        if (!confirm('Delete this conversation?')) {
            return;
        }

        try {
            await api.deleteConversation(id);
            this.list = this.list.filter(c => c.id !== id);

            // If we deleted the current conversation, clear the chat
            if (this.currentId === id) {
                this.currentId = null;
                chat.clear();
            }

            this.render();
        } catch (error) {
            console.error('Failed to delete conversation:', error);
        }
    },

    /**
     * Update a conversation's title in the list
     */
    updateTitle(id, title) {
        const conv = this.list.find(c => c.id === id);
        if (conv) {
            conv.title = title;
            this.render();
        }
    },

    /**
     * Move a conversation to the top of the list
     */
    moveToTop(id) {
        const index = this.list.findIndex(c => c.id === id);
        if (index > 0) {
            const [conv] = this.list.splice(index, 1);
            this.list.unshift(conv);
            this.render();
        }
    },

    /**
     * Close sidebar on mobile devices
     */
    closeSidebarOnMobile() {
        if (window.innerWidth <= 768) {
            document.getElementById('sidebar').classList.remove('open');
            document.querySelector('.sidebar-overlay')?.classList.remove('visible');
        }
    },

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
