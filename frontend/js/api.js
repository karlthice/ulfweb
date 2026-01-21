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
    },

    /**
     * Get available models from llama.cpp
     */
    async getModels() {
        const response = await fetch(`${API_BASE}/models`);
        if (!response.ok) {
            throw new Error('Failed to fetch models');
        }
        return response.json();
    },

    /**
     * Get active servers for chat dropdown
     */
    async getActiveServers() {
        const response = await fetch(`${API_BASE}/admin/servers/active`);
        if (!response.ok) {
            throw new Error('Failed to fetch servers');
        }
        return response.json();
    },

    // Document/Collection API methods
    /**
     * List all collections
     */
    async listCollections() {
        const response = await fetch(`${API_BASE}/documents/collections`);
        if (!response.ok) {
            throw new Error('Failed to fetch collections');
        }
        return response.json();
    },

    /**
     * Create a new collection
     */
    async createCollection(name, description = '') {
        const response = await fetch(`${API_BASE}/documents/collections`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create collection');
        }
        return response.json();
    },

    /**
     * Update a collection
     */
    async updateCollection(id, updates) {
        const response = await fetch(`${API_BASE}/documents/collections/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        if (!response.ok) {
            throw new Error('Failed to update collection');
        }
        return response.json();
    },

    /**
     * Delete a collection
     */
    async deleteCollection(id) {
        const response = await fetch(`${API_BASE}/documents/collections/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete collection');
        }
        return true;
    }
};
