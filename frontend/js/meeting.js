/**
 * Meeting dictation with speaker diarization
 */

const meeting = {
    mediaRecorder: null,
    isRecording: false,
    isProcessing: false,
    sessionId: null,
    chunkIndex: 0,
    pendingUploads: [],
    recordingStartTime: null,
    timerInterval: null,
    audioContext: null,
    analyser: null,
    animationFrameId: null,

    init() {
        this.meetingBtn = document.getElementById('meeting-btn');
        this.recordingIndicator = document.getElementById('meeting-recording-indicator');
        this.recordingTimer = document.getElementById('meeting-recording-timer');
        this.audioLevelCanvas = document.getElementById('meeting-audio-level');
        this.chunkStatusEl = document.getElementById('chunk-status');
        this.progressContainer = document.getElementById('meeting-progress');
        this.progressStatus = document.getElementById('meeting-progress-status');
        this.progressFill = document.getElementById('meeting-progress-fill');
        this.resultArea = document.getElementById('dictation-result');
        this.languageSelect = document.getElementById('dictation-language');
        this.dictateBtn = document.getElementById('dictate-btn');

        this.meetingBtn.addEventListener('click', () => {
            if (this.isRecording) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        });
    },

    formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return m + ':' + String(s).padStart(2, '0');
    },

    startTimer() {
        this.recordingStartTime = Date.now();
        this.updateTimerDisplay();
        this.timerInterval = setInterval(() => this.updateTimerDisplay(), 1000);
    },

    updateTimerDisplay() {
        const elapsed = Math.floor((Date.now() - this.recordingStartTime) / 1000);
        this.recordingTimer.textContent = 'Recording meeting... ' + this.formatTime(elapsed);
    },

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
        this.recordingStartTime = null;
    },

    startAudioLevel(stream) {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(stream);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            source.connect(this.analyser);

            const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
            const canvas = this.audioLevelCanvas;
            const ctx = canvas.getContext('2d');

            const draw = () => {
                this.animationFrameId = requestAnimationFrame(draw);
                this.analyser.getByteFrequencyData(dataArray);

                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    sum += dataArray[i];
                }
                const avg = sum / dataArray.length;
                const level = avg / 255;

                const w = canvas.width;
                const h = canvas.height;
                ctx.clearRect(0, 0, w, h);

                ctx.fillStyle = '#e5e7eb';
                ctx.beginPath();
                ctx.roundRect(0, 0, w, h, 4);
                ctx.fill();

                const barWidth = Math.max(0, level * w);
                if (barWidth > 0) {
                    let color;
                    if (level < 0.4) {
                        color = '#7c3aed';
                    } else if (level < 0.7) {
                        color = '#f59e0b';
                    } else {
                        color = '#ef4444';
                    }
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.roundRect(0, 0, barWidth, h, 4);
                    ctx.fill();
                }
            };

            draw();
        } catch (err) {
            console.warn('Audio level visualization not available:', err);
        }
    },

    stopAudioLevel() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
        if (this.audioContext) {
            this.audioContext.close().catch(() => {});
            this.audioContext = null;
            this.analyser = null;
        }
        if (this.audioLevelCanvas) {
            const ctx = this.audioLevelCanvas.getContext('2d');
            ctx.clearRect(0, 0, this.audioLevelCanvas.width, this.audioLevelCanvas.height);
        }
    },

    setButtonsDisabled(disabled) {
        this.meetingBtn.disabled = disabled;
        this.dictateBtn.disabled = disabled;
    },

    async startRecording() {
        if (!window.isSecureContext) {
            this.resultArea.value = 'Microphone requires a secure connection (HTTPS or localhost).';
            return;
        }

        try {
            // Create session on server
            const resp = await fetch('/api/v1/stt/meeting/start', { method: 'POST' });
            if (!resp.ok) throw new Error('Failed to create meeting session');
            const { session_id } = await resp.json();
            this.sessionId = session_id;
            this.chunkIndex = 0;
            this.pendingUploads = [];

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : 'audio/webm';

            this.mediaRecorder = new MediaRecorder(stream, { mimeType });

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    const p = this.uploadChunk(e.data);
                    this.pendingUploads.push(p);
                }
            };

            this.mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(track => track.stop());
                // Wait for all chunk uploads to finish before finalizing
                await Promise.all(this.pendingUploads);
                this.pendingUploads = [];
                this.finalize();
            };

            // Record in 60-second chunks
            this.mediaRecorder.start(60000);
            this.isRecording = true;

            this.meetingBtn.textContent = 'Stop meeting';
            this.meetingBtn.classList.add('recording');
            this.dictateBtn.disabled = true;
            this.recordingIndicator.classList.remove('hidden');
            this.chunkStatusEl.textContent = '';

            this.startTimer();
            this.startAudioLevel(stream);
        } catch (err) {
            console.error('Meeting recording error:', err);
            this.resultArea.value = 'Error: ' + err.message;
        }
    },

    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        this.isRecording = false;
        this.meetingBtn.textContent = 'Dictate meeting';
        this.meetingBtn.classList.remove('recording');
        this.recordingIndicator.classList.add('hidden');

        this.stopTimer();
        this.stopAudioLevel();
    },

    async uploadChunk(blob) {
        const index = this.chunkIndex++;
        const formData = new FormData();
        formData.append('audio', blob, `chunk_${index}.webm`);
        formData.append('chunk_index', index);

        try {
            const resp = await fetch(`/api/v1/stt/meeting/${this.sessionId}/chunk`, {
                method: 'POST',
                body: formData,
            });
            if (resp.ok) {
                this.chunkStatusEl.textContent = `${index + 1} chunks uploaded`;
            }
        } catch (err) {
            console.error('Chunk upload error:', err);
        }
    },

    async finalize() {
        this.isProcessing = true;
        this.setButtonsDisabled(true);
        this.resultArea.value = '';
        this.progressContainer.classList.remove('hidden');
        this.progressStatus.textContent = 'Processing...';
        this.progressFill.style.width = '0%';

        const formData = new FormData();
        const language = this.languageSelect.value;
        if (language) {
            formData.append('language', language);
        }

        try {
            const resp = await fetch(`/api/v1/stt/meeting/${this.sessionId}/finalize`, {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                throw new Error('Finalization failed');
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events from buffer
                const lines = buffer.split('\n');
                buffer = '';

                let eventType = null;
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ') && eventType) {
                        const data = JSON.parse(line.slice(6));
                        this.handleSSEEvent(eventType, data);
                        eventType = null;
                    } else if (line !== '') {
                        // Incomplete line, keep in buffer
                        buffer += line + '\n';
                    }
                }
            }
        } catch (err) {
            console.error('Meeting finalize error:', err);
            this.resultArea.value = 'Error: ' + err.message;
        } finally {
            this.isProcessing = false;
            this.setButtonsDisabled(false);
            this.progressContainer.classList.add('hidden');
        }
    },

    handleSSEEvent(event, data) {
        switch (event) {
            case 'progress':
                this.progressStatus.textContent = data.message;
                if (data.total_segments && data.completed_segments !== undefined) {
                    const pct = Math.round((data.completed_segments / data.total_segments) * 100);
                    this.progressFill.style.width = pct + '%';
                } else if (data.stage === 'assembling') {
                    this.progressFill.style.width = '5%';
                } else if (data.stage === 'diarizing') {
                    this.progressFill.style.width = '15%';
                }
                break;

            case 'transcript_line':
                if (this.resultArea.value) {
                    this.resultArea.value += '\n\n';
                }
                this.resultArea.value += data.line;
                // Scroll to bottom
                this.resultArea.scrollTop = this.resultArea.scrollHeight;
                break;

            case 'done':
                this.progressFill.style.width = '100%';
                this.progressStatus.textContent =
                    `Done: ${data.num_speakers} speakers, ${data.num_segments} segments (${data.duration}s)`;
                break;

            case 'error':
                this.resultArea.value = 'Error: ' + data.message;
                break;
        }
    },
};
