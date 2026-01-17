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
    await conversations.init();
    chat.init();
    await settingsModal.init();
    translate.init();

    console.log('ulfweb initialized');
})();

/**
 * Setup mode tab switching between Chat and Translate
 */
function setupModeTabs() {
    const chatTab = document.getElementById('chat-tab');
    const translateTab = document.getElementById('translate-tab');
    const chatPanel = document.getElementById('chat-panel');
    const translatePanel = document.getElementById('translate-panel');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationsList = document.getElementById('conversations-list');

    chatTab.addEventListener('click', () => {
        if (currentMode === 'chat') return;
        currentMode = 'chat';

        // Update tab states
        chatTab.classList.add('active');
        translateTab.classList.remove('active');

        // Show/hide panels
        chatPanel.classList.remove('hidden');
        translatePanel.classList.add('hidden');

        // Show chat-specific sidebar elements
        newChatBtn.classList.remove('hidden');
        conversationsList.classList.remove('hidden');
    });

    translateTab.addEventListener('click', () => {
        if (currentMode === 'translate') return;
        currentMode = 'translate';

        // Update tab states
        translateTab.classList.add('active');
        chatTab.classList.remove('active');

        // Show/hide panels
        translatePanel.classList.remove('hidden');
        chatPanel.classList.add('hidden');

        // Hide chat-specific sidebar elements
        newChatBtn.classList.add('hidden');
        conversationsList.classList.add('hidden');
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
