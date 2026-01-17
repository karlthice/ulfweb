/**
 * Translation module for TranslateGemma integration
 */

const translate = (function() {
    // Supported languages (sorted alphabetically by name)
    const LANGUAGES = [
        { code: 'af', name: 'Afrikaans' },
        { code: 'sq', name: 'Albanian' },
        { code: 'am', name: 'Amharic' },
        { code: 'ar', name: 'Arabic' },
        { code: 'hy', name: 'Armenian' },
        { code: 'az', name: 'Azerbaijani' },
        { code: 'eu', name: 'Basque' },
        { code: 'be', name: 'Belarusian' },
        { code: 'bn', name: 'Bengali' },
        { code: 'bs', name: 'Bosnian' },
        { code: 'bg', name: 'Bulgarian' },
        { code: 'ca', name: 'Catalan' },
        { code: 'zh', name: 'Chinese' },
        { code: 'hr', name: 'Croatian' },
        { code: 'cs', name: 'Czech' },
        { code: 'da', name: 'Danish' },
        { code: 'nl', name: 'Dutch' },
        { code: 'en', name: 'English' },
        { code: 'et', name: 'Estonian' },
        { code: 'fi', name: 'Finnish' },
        { code: 'fr', name: 'French' },
        { code: 'gl', name: 'Galician' },
        { code: 'ka', name: 'Georgian' },
        { code: 'de', name: 'German' },
        { code: 'el', name: 'Greek' },
        { code: 'gu', name: 'Gujarati' },
        { code: 'he', name: 'Hebrew' },
        { code: 'hi', name: 'Hindi' },
        { code: 'hu', name: 'Hungarian' },
        { code: 'is', name: 'Icelandic' },
        { code: 'id', name: 'Indonesian' },
        { code: 'ga', name: 'Irish' },
        { code: 'it', name: 'Italian' },
        { code: 'ja', name: 'Japanese' },
        { code: 'kn', name: 'Kannada' },
        { code: 'kk', name: 'Kazakh' },
        { code: 'ko', name: 'Korean' },
        { code: 'lv', name: 'Latvian' },
        { code: 'lt', name: 'Lithuanian' },
        { code: 'mk', name: 'Macedonian' },
        { code: 'ms', name: 'Malay' },
        { code: 'ml', name: 'Malayalam' },
        { code: 'mt', name: 'Maltese' },
        { code: 'mr', name: 'Marathi' },
        { code: 'mn', name: 'Mongolian' },
        { code: 'ne', name: 'Nepali' },
        { code: 'no', name: 'Norwegian' },
        { code: 'fa', name: 'Persian' },
        { code: 'pl', name: 'Polish' },
        { code: 'pt', name: 'Portuguese' },
        { code: 'pa', name: 'Punjabi' },
        { code: 'ro', name: 'Romanian' },
        { code: 'ru', name: 'Russian' },
        { code: 'sr', name: 'Serbian' },
        { code: 'si', name: 'Sinhala' },
        { code: 'sk', name: 'Slovak' },
        { code: 'sl', name: 'Slovenian' },
        { code: 'es', name: 'Spanish' },
        { code: 'sw', name: 'Swahili' },
        { code: 'sv', name: 'Swedish' },
        { code: 'ta', name: 'Tamil' },
        { code: 'te', name: 'Telugu' },
        { code: 'th', name: 'Thai' },
        { code: 'tr', name: 'Turkish' },
        { code: 'uk', name: 'Ukrainian' },
        { code: 'ur', name: 'Urdu' },
        { code: 'uz', name: 'Uzbek' },
        { code: 'vi', name: 'Vietnamese' },
        { code: 'cy', name: 'Welsh' },
        { code: 'zu', name: 'Zulu' }
    ];

    // LocalStorage keys
    const STORAGE_KEYS = {
        sourceLang: 'ulfweb_source_lang',
        targetLang: 'ulfweb_target_lang'
    };

    // DOM elements
    let sourceLanguageSelect;
    let targetLanguageSelect;
    let sourceTextArea;
    let targetTextArea;
    let translateBtn;
    let stopBtn;
    let swapBtn;

    // State
    let abortController = null;

    /**
     * Initialize the translation module
     */
    function init() {
        // Get DOM elements
        sourceLanguageSelect = document.getElementById('source-language');
        targetLanguageSelect = document.getElementById('target-language');
        sourceTextArea = document.getElementById('source-text');
        targetTextArea = document.getElementById('target-text');
        translateBtn = document.getElementById('translate-btn');
        stopBtn = document.getElementById('translate-stop-btn');
        swapBtn = document.getElementById('swap-languages');

        // Populate language dropdowns
        populateLanguageDropdowns();

        // Load saved language preferences
        loadSavedLanguages();

        // Setup event listeners
        setupEventListeners();

        console.log('Translation module initialized');
    }

    /**
     * Populate language dropdown selects
     */
    function populateLanguageDropdowns() {
        LANGUAGES.forEach(lang => {
            const sourceOption = document.createElement('option');
            sourceOption.value = lang.code;
            sourceOption.textContent = lang.name;
            sourceLanguageSelect.appendChild(sourceOption);

            const targetOption = document.createElement('option');
            targetOption.value = lang.code;
            targetOption.textContent = lang.name;
            targetLanguageSelect.appendChild(targetOption);
        });
    }

    /**
     * Load saved language preferences from localStorage
     */
    function loadSavedLanguages() {
        const savedSource = localStorage.getItem(STORAGE_KEYS.sourceLang);
        const savedTarget = localStorage.getItem(STORAGE_KEYS.targetLang);

        if (savedSource && LANGUAGES.some(l => l.code === savedSource)) {
            sourceLanguageSelect.value = savedSource;
        } else {
            sourceLanguageSelect.value = 'en';
        }

        if (savedTarget && LANGUAGES.some(l => l.code === savedTarget)) {
            targetLanguageSelect.value = savedTarget;
        } else {
            targetLanguageSelect.value = 'es';
        }
    }

    /**
     * Save language preferences to localStorage
     */
    function saveLanguages() {
        localStorage.setItem(STORAGE_KEYS.sourceLang, sourceLanguageSelect.value);
        localStorage.setItem(STORAGE_KEYS.targetLang, targetLanguageSelect.value);
    }

    /**
     * Setup event listeners
     */
    function setupEventListeners() {
        // Translate button
        translateBtn.addEventListener('click', performTranslation);

        // Stop button
        stopBtn.addEventListener('click', stopTranslation);

        // Swap languages button
        swapBtn.addEventListener('click', swapLanguages);

        // Save language preferences on change
        sourceLanguageSelect.addEventListener('change', saveLanguages);
        targetLanguageSelect.addEventListener('change', saveLanguages);

        // Keyboard shortcut: Ctrl+Enter to translate
        sourceTextArea.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                performTranslation();
            }
        });
    }

    /**
     * Swap source and target languages and text
     */
    function swapLanguages() {
        // Swap language selections
        const tempLang = sourceLanguageSelect.value;
        sourceLanguageSelect.value = targetLanguageSelect.value;
        targetLanguageSelect.value = tempLang;

        // Swap text content
        const tempText = sourceTextArea.value;
        sourceTextArea.value = targetTextArea.value;
        targetTextArea.value = tempText;

        // Save preferences
        saveLanguages();
    }

    /**
     * Perform translation with SSE streaming
     */
    async function performTranslation() {
        const text = sourceTextArea.value.trim();
        if (!text) {
            return;
        }

        const sourceLang = sourceLanguageSelect.value;
        const targetLang = targetLanguageSelect.value;

        if (sourceLang === targetLang) {
            targetTextArea.value = text;
            return;
        }

        // Abort any existing translation
        stopTranslation();

        // Create new abort controller
        abortController = new AbortController();

        // Update UI state
        translateBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
        targetTextArea.value = '';
        targetTextArea.classList.add('streaming');

        try {
            const response = await fetch('/api/v1/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    source_lang: sourceLang,
                    target_lang: targetLang
                }),
                signal: abortController.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    break;
                }

                buffer += decoder.decode(value, { stream: true });

                // Process complete SSE messages
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        try {
                            const parsed = JSON.parse(data);

                            if (parsed.type === 'content') {
                                targetTextArea.value += parsed.content;
                            } else if (parsed.type === 'done') {
                                // Translation complete
                            } else if (parsed.type === 'error') {
                                targetTextArea.value = `Error: ${parsed.content}`;
                            }
                        } catch (e) {
                            // Skip invalid JSON
                        }
                    }
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                // Translation was intentionally stopped
            } else {
                targetTextArea.value = `Error: ${error.message}`;
            }
        } finally {
            // Reset UI state
            translateBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
            targetTextArea.classList.remove('streaming');
            abortController = null;
        }
    }

    /**
     * Stop the current translation
     */
    function stopTranslation() {
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }

    /**
     * Check if translation is in progress
     */
    function isTranslating() {
        return abortController !== null;
    }

    return {
        init,
        performTranslation,
        stopTranslation,
        swapLanguages,
        isTranslating
    };
})();
