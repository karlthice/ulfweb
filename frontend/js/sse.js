/**
 * SSE (Server-Sent Events) handler for streaming chat responses
 */

class SSEHandler {
    constructor() {
        this.abortController = null;
    }

    /**
     * Send a message and stream the response
     * @param {number} conversationId - The conversation ID
     * @param {string} content - The message content
     * @param {function} onChunk - Callback for each content chunk
     * @param {function} onDone - Callback when streaming is complete
     * @param {function} onError - Callback for errors
     * @param {string|null} imageBase64 - Optional base64-encoded image
     */
    async streamMessage(conversationId, content, onChunk, onDone, onError, imageBase64 = null) {
        // Abort any existing stream
        this.abort();

        this.abortController = new AbortController();

        try {
            const body = { content };
            if (imageBase64) {
                body.image = imageBase64;
            }

            const response = await fetch(`/api/v1/chat/${conversationId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: this.abortController.signal
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
                                onChunk(parsed.content);
                            } else if (parsed.type === 'done') {
                                onDone(parsed.message_id);
                            } else if (parsed.type === 'error') {
                                onError(parsed.content);
                            }
                        } catch (e) {
                            // Skip invalid JSON
                        }
                    }
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                // Stream was intentionally aborted
                onDone(null);
            } else {
                onError(error.message);
            }
        } finally {
            this.abortController = null;
        }
    }

    /**
     * Abort the current stream
     */
    abort() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    /**
     * Check if streaming is active
     */
    isStreaming() {
        return this.abortController !== null;
    }
}

// Global SSE handler instance
const sseHandler = new SSEHandler();
