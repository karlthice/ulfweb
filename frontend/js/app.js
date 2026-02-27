/**
 * Main application entry point
 */

// Track current mode
let currentMode = 'chat';

(async function() {
    // Initialize sidebar toggle for mobile
    setupMobileSidebar();

    // Initialize tab switching
    setupModeTabs();

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

    console.log('ulfweb initialized');
})();

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
