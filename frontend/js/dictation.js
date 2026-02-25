/**
 * Dictation (Speech-to-Text) functionality
 */

const dictation = {
    mediaRecorder: null,
    audioChunks: [],
    isRecording: false,

    init() {
        this.dictateBtn = document.getElementById('dictate-btn');
        this.recordingIndicator = document.getElementById('recording-indicator');
        this.resultArea = document.getElementById('dictation-result');
        this.copyBtn = document.getElementById('dictation-copy-btn');
        this.languageSelect = document.getElementById('dictation-language');
        this.micStatus = document.getElementById('mic-status');

        this.dictateBtn.addEventListener('click', () => {
            if (this.isRecording) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        });

        this.copyBtn.addEventListener('click', () => {
            if (this.resultArea.value) {
                navigator.clipboard.writeText(this.resultArea.value);
                this.copyBtn.textContent = 'Copied!';
                setTimeout(() => { this.copyBtn.textContent = 'Copy'; }, 1500);
            }
        });

        this.checkMicrophoneSupport();
    },

    /**
     * Check if microphone access is available and show status
     */
    async checkMicrophoneSupport() {
        // Check for secure context (HTTPS or localhost)
        if (!window.isSecureContext) {
            this.showMicStatus(
                'error',
                'Microphone requires a secure connection (HTTPS). ' +
                'Access this page via https:// or localhost.'
            );
            this.dictateBtn.disabled = true;
            return;
        }

        // Check for getUserMedia API
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.showMicStatus('error', 'Your browser does not support microphone access.');
            this.dictateBtn.disabled = true;
            return;
        }

        // Check current permission state if Permissions API is available
        if (navigator.permissions) {
            try {
                const result = await navigator.permissions.query({ name: 'microphone' });
                this.updatePermissionStatus(result.state);
                result.addEventListener('change', () => {
                    this.updatePermissionStatus(result.state);
                });
            } catch {
                // Permissions API query not supported for microphone in some browsers
                this.showMicStatus('info', 'Click Dictate to allow microphone access.');
            }
        } else {
            this.showMicStatus('info', 'Click Dictate to allow microphone access.');
        }
    },

    /**
     * Update UI based on permission state
     */
    updatePermissionStatus(state) {
        if (state === 'granted') {
            this.showMicStatus('ok', 'Microphone access granted.');
            this.dictateBtn.disabled = false;
        } else if (state === 'denied') {
            this.showMicStatus(
                'error',
                'Microphone access denied. Click the lock/site-settings icon in your browser\'s address bar to allow microphone access, then reload the page.'
            );
            this.dictateBtn.disabled = true;
        } else {
            // 'prompt' — permission not yet requested
            this.showMicStatus('info', 'Click Dictate to allow microphone access.');
            this.dictateBtn.disabled = false;
        }
    },

    /**
     * Show microphone status message
     */
    showMicStatus(level, message) {
        if (!this.micStatus) return;
        this.micStatus.textContent = message;
        this.micStatus.className = 'mic-status mic-status-' + level;
        this.micStatus.classList.remove('hidden');
    },

    async startRecording() {
        // Check secure context before attempting
        if (!window.isSecureContext) {
            this.showMicStatus(
                'error',
                'Microphone requires a secure connection (HTTPS). ' +
                'Access this page via https:// or localhost.'
            );
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Permission granted — update status
            this.showMicStatus('ok', 'Microphone access granted.');

            this.audioChunks = [];

            // Pick a supported mime type
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : 'audio/webm';

            this.mediaRecorder = new MediaRecorder(stream, { mimeType });

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    this.audioChunks.push(e.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                // Stop all tracks to release the microphone
                stream.getTracks().forEach(track => track.stop());
                const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.transcribe(blob);
            };

            this.mediaRecorder.start();
            this.isRecording = true;
            this.dictateBtn.textContent = 'Stop';
            this.dictateBtn.classList.add('recording');
            this.recordingIndicator.classList.remove('hidden');
        } catch (err) {
            console.error('Microphone error:', err);
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                this.showMicStatus(
                    'error',
                    'Microphone access denied. Click the lock/site-settings icon in your browser\'s address bar to allow microphone access, then reload the page.'
                );
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                this.showMicStatus('error', 'No microphone found. Please connect a microphone and try again.');
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                this.showMicStatus('error', 'Microphone is in use by another application. Close it and try again.');
            } else {
                this.showMicStatus('error', 'Microphone error: ' + err.message);
            }
        }
    },

    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        this.isRecording = false;
        this.dictateBtn.textContent = 'Dictate';
        this.dictateBtn.classList.remove('recording');
        this.recordingIndicator.classList.add('hidden');
    },

    async transcribe(blob) {
        this.resultArea.value = 'Transcribing...';
        this.dictateBtn.disabled = true;

        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');

        const language = this.languageSelect.value;
        if (language) {
            formData.append('language', language);
        }

        try {
            const response = await fetch('/api/v1/stt', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Transcription failed');
            }

            const data = await response.json();
            this.resultArea.value = data.text || '(no speech detected)';
        } catch (err) {
            console.error('Transcription error:', err);
            this.resultArea.value = 'Error: ' + err.message;
        } finally {
            this.dictateBtn.disabled = false;
        }
    }
};
