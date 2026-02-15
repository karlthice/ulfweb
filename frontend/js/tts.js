/**
 * Text-to-Speech module for ULF Web
 */

const tts = (function() {
    // Audio element for playback
    let audioElement = null;
    let currentButton = null;

    /**
     * Initialize TTS module
     */
    function init() {
        audioElement = new Audio();
        audioElement.addEventListener('ended', onPlaybackEnded);
        audioElement.addEventListener('error', onPlaybackError);
        console.log('TTS module initialized');
    }

    /**
     * Handle playback ended
     */
    function onPlaybackEnded() {
        if (currentButton) {
            currentButton.classList.remove('speaking');
            currentButton = null;
        }
    }

    /**
     * Handle playback error
     */
    function onPlaybackError(e) {
        console.error('TTS playback error:', e);
        if (currentButton) {
            currentButton.classList.remove('speaking');
            currentButton = null;
        }
    }

    /**
     * Speak text using TTS API
     * @param {string} text - Text to speak
     * @param {string|null} language - Language code (auto-detect if null)
     * @param {HTMLElement|null} button - Button element to show speaking state
     */
    async function speak(text, language = null, button = null) {
        if (!text || !text.trim()) {
            return;
        }

        // Stop any current playback
        stop();

        // Set button state
        if (button) {
            currentButton = button;
            button.classList.add('speaking');
        }

        try {
            const response = await fetch('/api/v1/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text.trim(),
                    language: language
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'TTS request failed');
            }

            // Get audio data as blob
            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);

            // Play audio
            audioElement.src = audioUrl;
            await audioElement.play();

            // Clean up URL after playback
            audioElement.onended = () => {
                URL.revokeObjectURL(audioUrl);
                onPlaybackEnded();
            };

        } catch (error) {
            console.error('TTS error:', error);
            if (currentButton) {
                currentButton.classList.remove('speaking');
                currentButton = null;
            }
        }
    }

    /**
     * Stop current playback
     */
    function stop() {
        if (audioElement) {
            audioElement.pause();
            audioElement.currentTime = 0;
        }
        if (currentButton) {
            currentButton.classList.remove('speaking');
            currentButton = null;
        }
    }

    /**
     * Check if currently speaking
     * @returns {boolean}
     */
    function isSpeaking() {
        return audioElement && !audioElement.paused;
    }

    /**
     * Create a speak button element
     * @param {Function} getTextFn - Function that returns the text to speak
     * @param {string|null} language - Optional fixed language
     * @returns {HTMLButtonElement}
     */
    function createSpeakButton(getTextFn, language = null) {
        const button = document.createElement('button');
        button.className = 'speak-btn';
        button.title = 'Speak';
        button.innerHTML = '<span class="speak-icon">&#128266;</span>';

        button.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (button.classList.contains('speaking')) {
                stop();
            } else {
                const text = getTextFn();
                speak(text, language, button);
            }
        });

        return button;
    }

    /**
     * Extract plain text from HTML content
     * @param {string} html - HTML content
     * @returns {string} - Plain text
     */
    function htmlToText(html) {
        const temp = document.createElement('div');
        temp.innerHTML = html;
        return temp.textContent || temp.innerText || '';
    }

    return {
        init,
        speak,
        stop,
        isSpeaking,
        createSpeakButton,
        htmlToText
    };
})();
