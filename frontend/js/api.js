/**
 * API client for ulfweb backend
 */

const API_BASE = '/api/v1';

// Global 401 interceptor — redirect to /login on auth failure
const _origFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await _origFetch.apply(this, args);
    if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        // Don't redirect for auth endpoints themselves
        if (!url.includes('/auth/login') && !url.includes('/auth/mode') && !url.includes('/auth/me')) {
            window.location.href = '/login';
        }
    }
    return response;
};

const api = {
    // Auth API methods

    async getAuthMode() {
        const response = await fetch(`${API_BASE}/auth/mode`);
        if (!response.ok) throw new Error('Failed to check auth mode');
        return response.json();
    },

    async getCurrentUser() {
        const response = await fetch(`${API_BASE}/auth/me`);
        if (!response.ok) return null;
        return response.json();
    },

    async login(username, password) {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Login failed');
        }
        return response.json();
    },

    async logout() {
        const response = await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
        return response.ok;
    },

    async changePassword(currentPassword, newPassword) {
        const response = await fetch(`${API_BASE}/auth/password`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to change password');
        }
        return response.json();
    },

    // User management API methods (admin)

    async listUsers() {
        const response = await fetch(`${API_BASE}/users`);
        if (!response.ok) throw new Error('Failed to fetch users');
        return response.json();
    },

    async createUser(data) {
        const response = await fetch(`${API_BASE}/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to create user');
        }
        return response.json();
    },

    async updateUser(id, data) {
        const response = await fetch(`${API_BASE}/users/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to update user');
        }
        return response.json();
    },

    async setUserPassword(id, password) {
        const response = await fetch(`${API_BASE}/users/${id}/password`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to set password');
        }
        return response.json();
    },

    async deleteUser(id) {
        const response = await fetch(`${API_BASE}/users/${id}`, { method: 'DELETE' });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to delete user');
        }
        return true;
    },

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
    },

    // Vault API methods

    async listVaultCases() {
        const response = await fetch(`${API_BASE}/vault/cases`);
        if (!response.ok) throw new Error('Failed to fetch cases');
        return response.json();
    },

    async createVaultCase(data) {
        const response = await fetch(`${API_BASE}/vault/cases`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create case');
        }
        return response.json();
    },

    async getVaultCase(id) {
        const response = await fetch(`${API_BASE}/vault/cases/${id}`);
        if (!response.ok) {
            if (response.status === 404) return null;
            throw new Error('Failed to fetch case');
        }
        return response.json();
    },

    async updateVaultCase(id, updates) {
        const response = await fetch(`${API_BASE}/vault/cases/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to update case');
        }
        return response.json();
    },

    async deleteVaultCase(id) {
        const response = await fetch(`${API_BASE}/vault/cases/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to delete case');
        }
        return true;
    },

    async searchVaultCases(query) {
        const response = await fetch(`${API_BASE}/vault/cases/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Failed to search cases');
        return response.json();
    },

    async addVaultRecord(caseId, formData) {
        const response = await fetch(`${API_BASE}/vault/cases/${caseId}/records`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to add record');
        }
        return response.json();
    },

    async toggleVaultRecordStar(recordId) {
        const response = await fetch(`${API_BASE}/vault/records/${recordId}/star`, {
            method: 'PUT'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to toggle star');
        }
        return response.json();
    },

    async updateVaultRecord(recordId, updates) {
        const response = await fetch(`${API_BASE}/vault/records/${recordId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update record');
        }
        return response.json();
    },

    async deleteVaultRecord(recordId) {
        const response = await fetch(`${API_BASE}/vault/records/${recordId}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to delete record');
        }
        return true;
    },

    async searchVaultRecords(query, caseId = null) {
        let url = `${API_BASE}/vault/records/search?q=${encodeURIComponent(query)}`;
        if (caseId) url += `&case_id=${caseId}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to search records');
        return response.json();
    },

    getVaultRecordFileUrl(recordId) {
        return `${API_BASE}/vault/records/${recordId}/file`;
    },

    getVaultCaseExportUrl(caseId) {
        return `${API_BASE}/vault/cases/${caseId}/export`;
    },

    async extractDocumentText(file) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch(`${API_BASE}/documents/extract-text`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Failed to extract text');
        }
        return response.json();
    },

    async getDateFormat() {
        try {
            const response = await fetch(`${API_BASE}/admin/date-format`);
            if (!response.ok) return 'YYYY-MM-DD';
            const data = await response.json();
            return data.date_format || 'YYYY-MM-DD';
        } catch {
            return 'YYYY-MM-DD';
        }
    }
};
