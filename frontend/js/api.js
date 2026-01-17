/**
 * API client for ulfweb backend
 */

const API_BASE = '/api/v1';

const api = {
    /**
     * List all conversations
     */
    async listConversations() {
        const response = await fetch(`${API_BASE}/conversations`);
        if (!response.ok) {
            throw new Error('Failed to fetch conversations');
        }
        return response.json();
    },

    /**
     * Create a new conversation
     */
    async createConversation(title = 'New Conversation') {
        const response = await fetch(`${API_BASE}/conversations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        if (!response.ok) {
            throw new Error('Failed to create conversation');
        }
        return response.json();
    },

    /**
     * Get a conversation with messages
     */
    async getConversation(id) {
        const response = await fetch(`${API_BASE}/conversations/${id}`);
        if (!response.ok) {
            if (response.status === 404) {
                return null;
            }
            throw new Error('Failed to fetch conversation');
        }
        return response.json();
    },

    /**
     * Update a conversation's title
     */
    async updateConversation(id, title) {
        const response = await fetch(`${API_BASE}/conversations/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        if (!response.ok) {
            throw new Error('Failed to update conversation');
        }
        return response.json();
    },

    /**
     * Delete a conversation
     */
    async deleteConversation(id) {
        const response = await fetch(`${API_BASE}/conversations/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok && response.status !== 204) {
            throw new Error('Failed to delete conversation');
        }
        return true;
    },

    /**
     * Get user settings
     */
    async getSettings() {
        const response = await fetch(`${API_BASE}/settings`);
        if (!response.ok) {
            throw new Error('Failed to fetch settings');
        }
        return response.json();
    },

    /**
     * Update user settings
     */
    async updateSettings(settings) {
        const response = await fetch(`${API_BASE}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        if (!response.ok) {
            throw new Error('Failed to update settings');
        }
        return response.json();
    }
};
