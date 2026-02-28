/**
 * Main application entry point
 */

// Track current mode
let currentMode = 'chat';

// Current user info (set during auth check)
window.currentUser = null;

(async function() {
    // Auth gate: check if login is required
    try {
        const mode = await api.getAuthMode();
        if (!mode.single_user) {
            // Not single-user mode — verify session
            const user = await api.getCurrentUser();
            if (!user) {
                window.location.href = '/login';
                return;
            }
            window.currentUser = user;
        } else {
            // Single-user mode — get user info
            const user = await api.getCurrentUser();
            window.currentUser = user;
        }
    } catch (e) {
        console.error('Auth check failed:', e);
    }

    // Initialize sidebar toggle for mobile
    setupMobileSidebar();

    // Initialize tab switching
    setupModeTabs();

    // Initialize user badge
    setupUserBadge();

    // Initialize components
    tts.init();
    await conversations.init();
    chat.init();
    await settingsModal.init();
    translate.init();
    documents.init();
    dictation.init();
    meeting.init();
    vault.init();

    // Hide admin-only controls for non-admin users
    applyUserPermissions();

    console.log('ulfweb initialized');
})();

/**
 * Apply UI visibility based on user permissions
 */
function applyUserPermissions() {
    if (!window.currentUser || window.currentUser.usertype !== 'admin') {
        // Hide settings button
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) settingsBtn.style.display = 'none';
    }
}

/**
 * Setup user badge in sidebar
 */
function setupUserBadge() {
    const badge = document.getElementById('user-badge');
    const logoutBtn = document.getElementById('logout-btn');
    if (!badge || !window.currentUser) return;

    badge.textContent = window.currentUser.username;
    badge.title = 'Change password';
    badge.addEventListener('click', () => openPasswordModal());

    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            await api.logout();
            window.location.href = '/login';
        });
    }
}

/**
 * Open the password change modal
 */
function openPasswordModal() {
    const modal = document.getElementById('password-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.getElementById('current-password').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
        document.getElementById('password-error').textContent = '';
        document.getElementById('current-password').focus();
    }
}

// Password modal event listeners (set up once DOM is ready)
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('password-modal');
    if (!modal) return;

    document.getElementById('close-password-modal').addEventListener('click', () => {
        modal.classList.add('hidden');
    });
    document.getElementById('password-modal-overlay').addEventListener('click', () => {
        modal.classList.add('hidden');
    });
    document.getElementById('save-password-btn').addEventListener('click', async () => {
        const errorEl = document.getElementById('password-error');
        const current = document.getElementById('current-password').value;
        const newPw = document.getElementById('new-password').value;
        const confirm = document.getElementById('confirm-password').value;

        errorEl.textContent = '';

        if (!current || !newPw) {
            errorEl.textContent = 'All fields are required';
            return;
        }
        if (newPw !== confirm) {
            errorEl.textContent = 'New passwords do not match';
            return;
        }

        try {
            await api.changePassword(current, newPw);
            modal.classList.add('hidden');
        } catch (e) {
            errorEl.textContent = e.message;
        }
    });
});

/**
 * Setup mode tab switching between Chat, Translate, and Documents
 */
function setupModeTabs() {
    const chatTab = document.getElementById('chat-tab');
    const translateTab = document.getElementById('translate-tab');
    const documentsTab = document.getElementById('documents-tab');
    const dictationTab = document.getElementById('dictation-tab');
    const vaultTab = document.getElementById('vault-tab');
    const chatPanel = document.getElementById('chat-panel');
    const translatePanel = document.getElementById('translate-panel');
    const documentsPanel = document.getElementById('documents-panel');
    const dictationPanel = document.getElementById('dictation-panel');
    const vaultPanel = document.getElementById('vault-panel');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationsList = document.getElementById('conversations-list');

    function setActiveTab(mode) {
        currentMode = mode;

        // Update tab states
        chatTab.classList.toggle('active', mode === 'chat');
        translateTab.classList.toggle('active', mode === 'translate');
        documentsTab.classList.toggle('active', mode === 'documents');
        dictationTab.classList.toggle('active', mode === 'dictation');
        vaultTab.classList.toggle('active', mode === 'vault');

        // Show/hide panels
        chatPanel.classList.toggle('hidden', mode !== 'chat');
        translatePanel.classList.toggle('hidden', mode !== 'translate');
        documentsPanel.classList.toggle('hidden', mode !== 'documents');
        dictationPanel.classList.toggle('hidden', mode !== 'dictation');
        vaultPanel.classList.toggle('hidden', mode !== 'vault');

        // Show/hide chat-specific sidebar elements
        conversationsList.classList.toggle('hidden', mode !== 'chat');

        // Load vault data when switching to vault tab
        if (mode === 'vault') {
            vault.loadCases();
        }
    }

    chatTab.addEventListener('click', () => {
        if (currentMode !== 'chat') setActiveTab('chat');
    });

    translateTab.addEventListener('click', () => {
        if (currentMode !== 'translate') setActiveTab('translate');
    });

    documentsTab.addEventListener('click', () => {
        if (currentMode !== 'documents') setActiveTab('documents');
    });

    dictationTab.addEventListener('click', () => {
        if (currentMode !== 'dictation') setActiveTab('dictation');
    });

    vaultTab.addEventListener('click', () => {
        if (currentMode !== 'vault') setActiveTab('vault');
    });
}

/**
 * Setup mobile sidebar functionality
 */
function setupMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebar-toggle');

    // Create overlay element
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);

    // Toggle sidebar
    toggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('visible');
    });

    // Close on overlay click
    overlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('visible');
    });

    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            overlay.classList.remove('visible');
        }
    });
}
