/**
 * Settings modal management
 */

const settingsModal = {
    settings: null,

    /**
     * Initialize settings
     */
    async init() {
        await this.load();
        this.setupEventListeners();
    },

    /**
     * Load settings from server
     */
    async load() {
        try {
            this.settings = await api.getSettings();
            this.updateUI();
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const modal = document.getElementById('settings-modal');
        const openBtn = document.getElementById('settings-btn');
        const closeBtn = document.getElementById('close-settings');
        const overlay = document.getElementById('modal-overlay');
        const saveBtn = document.getElementById('save-settings');

        // Open modal
        openBtn.addEventListener('click', () => this.open());

        // Close modal
        closeBtn.addEventListener('click', () => this.close());
        overlay.addEventListener('click', () => this.close());

        // Save settings
        saveBtn.addEventListener('click', () => this.save());

        // Update value displays for sliders
        this.setupSliderListeners();

        // Close on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
                this.close();
            }
        });
    },

    /**
     * Setup slider value display listeners
     */
    setupSliderListeners() {
        const sliders = [
            { id: 'temperature', display: 'temperature-value' },
            { id: 'top-k', display: 'top-k-value' },
            { id: 'top-p', display: 'top-p-value' },
            { id: 'repeat-penalty', display: 'repeat-penalty-value' },
            { id: 'max-tokens', display: 'max-tokens-value' }
        ];

        for (const slider of sliders) {
            const input = document.getElementById(slider.id);
            const display = document.getElementById(slider.display);

            input.addEventListener('input', () => {
                display.textContent = input.value;
            });
        }
    },

    /**
     * Update UI with current settings
     */
    updateUI() {
        if (!this.settings) return;

        document.getElementById('temperature').value = this.settings.temperature;
        document.getElementById('temperature-value').textContent = this.settings.temperature;

        document.getElementById('top-k').value = this.settings.top_k;
        document.getElementById('top-k-value').textContent = this.settings.top_k;

        document.getElementById('top-p').value = this.settings.top_p;
        document.getElementById('top-p-value').textContent = this.settings.top_p;

        document.getElementById('repeat-penalty').value = this.settings.repeat_penalty;
        document.getElementById('repeat-penalty-value').textContent = this.settings.repeat_penalty;

        document.getElementById('max-tokens').value = this.settings.max_tokens;
        document.getElementById('max-tokens-value').textContent = this.settings.max_tokens;

        document.getElementById('system-prompt').value = this.settings.system_prompt || '';
    },

    /**
     * Open the settings modal
     */
    open() {
        document.getElementById('settings-modal').classList.remove('hidden');
        this.updateUI();
    },

    /**
     * Close the settings modal
     */
    close() {
        document.getElementById('settings-modal').classList.add('hidden');
    },

    /**
     * Save settings
     */
    async save() {
        const newSettings = {
            temperature: parseFloat(document.getElementById('temperature').value),
            top_k: parseInt(document.getElementById('top-k').value),
            top_p: parseFloat(document.getElementById('top-p').value),
            repeat_penalty: parseFloat(document.getElementById('repeat-penalty').value),
            max_tokens: parseInt(document.getElementById('max-tokens').value),
            system_prompt: document.getElementById('system-prompt').value
        };

        try {
            this.settings = await api.updateSettings(newSettings);
            this.close();
        } catch (error) {
            console.error('Failed to save settings:', error);
            alert('Failed to save settings. Please try again.');
        }
    }
};
