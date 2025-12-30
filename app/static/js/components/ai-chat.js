/**
 * AI Chat Widget for Scheduling Assistant
 * Uses local Ollama LLM with RAG for context-aware responses
 */

class SchedulerAIChat {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`AI Chat: Container #${containerId} not found`);
            return;
        }

        this.options = {
            apiBase: '/api/ai/rag',
            maxMessageLength: 2000,
            streamResponses: false,  // Set to true when streaming is stable
            ...options
        };

        this.messages = [];
        this.isLoading = false;
        this.isMinimized = false;

        this.init();
    }

    init() {
        this.render();
        this.attachEventListeners();
        this.checkHealth();
    }

    render() {
        this.container.innerHTML = `
            <div class="ai-chat-widget ${this.isMinimized ? 'minimized' : ''}">
                <div class="ai-chat-header" id="ai-chat-header">
                    <div class="ai-chat-title">
                        <span class="ai-icon">🤖</span>
                        <h3>Scheduling Assistant</h3>
                    </div>
                    <div class="ai-chat-controls">
                        <span class="ai-status" id="ai-status">Checking...</span>
                        <button class="ai-minimize-btn" id="ai-minimize" title="Minimize">
                            <span>−</span>
                        </button>
                    </div>
                </div>
                <div class="ai-chat-body">
                    <div class="ai-chat-messages" id="ai-messages">
                        <div class="ai-message assistant">
                            <div class="ai-message-content">
                                <p>Hello! I'm your scheduling assistant. I can help you with:</p>
                                <ul>
                                    <li>Employee availability</li>
                                    <li>Schedule conflicts</li>
                                    <li>Assignment suggestions</li>
                                    <li>Workload analysis</li>
                                </ul>
                                <p class="ai-hint">Try asking: "Who is available tomorrow?"</p>
                            </div>
                        </div>
                    </div>
                    <div class="ai-chat-input-container">
                        <div class="ai-quick-actions" id="ai-quick-actions">
                            <button class="ai-quick-btn" data-query="Who is available today?">Available today</button>
                            <button class="ai-quick-btn" data-query="Are there any scheduling conflicts this week?">Check conflicts</button>
                            <button class="ai-quick-btn" data-query="Show workload summary for this week">Workload</button>
                        </div>
                        <div class="ai-chat-input">
                            <textarea
                                id="ai-input"
                                placeholder="Ask about schedules..."
                                maxlength="${this.options.maxMessageLength}"
                                rows="1"
                            ></textarea>
                            <button id="ai-send" class="ai-send-btn" title="Send message">
                                <svg viewBox="0 0 24 24" width="20" height="20">
                                    <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const input = document.getElementById('ai-input');
        const sendBtn = document.getElementById('ai-send');
        const minimizeBtn = document.getElementById('ai-minimize');
        const header = document.getElementById('ai-chat-header');
        const quickActions = document.getElementById('ai-quick-actions');

        // Send button click
        sendBtn.addEventListener('click', () => this.sendMessage());

        // Enter key to send (Shift+Enter for newline)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        // Minimize toggle
        minimizeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleMinimize();
        });

        // Click header to expand when minimized
        header.addEventListener('click', () => {
            if (this.isMinimized) {
                this.toggleMinimize();
            }
        });

        // Quick action buttons
        quickActions.addEventListener('click', (e) => {
            if (e.target.classList.contains('ai-quick-btn')) {
                const query = e.target.dataset.query;
                if (query) {
                    document.getElementById('ai-input').value = query;
                    this.sendMessage();
                }
            }
        });
    }

    toggleMinimize() {
        this.isMinimized = !this.isMinimized;
        const widget = this.container.querySelector('.ai-chat-widget');
        const minimizeBtn = document.getElementById('ai-minimize');

        if (this.isMinimized) {
            widget.classList.add('minimized');
            minimizeBtn.innerHTML = '<span>+</span>';
            minimizeBtn.title = 'Expand';
        } else {
            widget.classList.remove('minimized');
            minimizeBtn.innerHTML = '<span>−</span>';
            minimizeBtn.title = 'Minimize';
            // Focus input when expanded
            setTimeout(() => document.getElementById('ai-input')?.focus(), 100);
        }
    }

    async checkHealth() {
        const statusEl = document.getElementById('ai-status');

        try {
            const response = await fetch(`${this.options.apiBase}/health`);
            const data = await response.json();

            if (data.status === 'healthy') {
                statusEl.textContent = 'Online';
                statusEl.className = 'ai-status online';
            } else if (data.status === 'disabled') {
                statusEl.textContent = 'Disabled';
                statusEl.className = 'ai-status disabled';
            } else {
                statusEl.textContent = 'Offline';
                statusEl.className = 'ai-status offline';
                statusEl.title = data.message || 'Ollama not available';
            }
        } catch (error) {
            statusEl.textContent = 'Error';
            statusEl.className = 'ai-status error';
            statusEl.title = error.message;
        }
    }

    async sendMessage() {
        const input = document.getElementById('ai-input');
        const message = input.value.trim();

        if (!message || this.isLoading) return;

        // Add user message to UI
        this.addMessage('user', message);
        input.value = '';
        input.style.height = 'auto';

        // Show loading indicator
        this.isLoading = true;
        const loadingId = this.addMessage('assistant', '', true);

        try {
            const response = await fetch(`${this.options.apiBase}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken(),
                },
                body: JSON.stringify({ message }),
            });

            const data = await response.json();

            // Remove loading message
            this.removeMessage(loadingId);

            if (data.error) {
                this.addMessage('assistant', `Error: ${data.error}`, false, true);
            } else {
                this.addMessage('assistant', data.answer, false, false, data.metadata);
            }

        } catch (error) {
            this.removeMessage(loadingId);
            this.addMessage('assistant', 'Failed to get response. Please check if Ollama is running.', false, true);
            console.error('AI Chat error:', error);
        } finally {
            this.isLoading = false;
        }
    }

    addMessage(role, content, isLoading = false, isError = false, metadata = null) {
        const messagesEl = document.getElementById('ai-messages');
        const id = Date.now();

        const messageEl = document.createElement('div');
        messageEl.className = `ai-message ${role}${isError ? ' error' : ''}`;
        messageEl.id = `msg-${id}`;

        if (isLoading) {
            messageEl.innerHTML = `
                <div class="ai-message-content">
                    <div class="ai-loading">
                        <span class="ai-loading-dot"></span>
                        <span class="ai-loading-dot"></span>
                        <span class="ai-loading-dot"></span>
                    </div>
                </div>
            `;
        } else {
            const formattedContent = this.formatMessage(content);
            let html = `<div class="ai-message-content">${formattedContent}</div>`;

            if (metadata && role === 'assistant') {
                html += `
                    <div class="ai-message-meta">
                        <span class="ai-meta-type">${metadata.query_type}</span>
                        <span class="ai-meta-time">${metadata.processing_time_ms}ms</span>
                    </div>
                `;
            }

            messageEl.innerHTML = html;
        }

        messagesEl.appendChild(messageEl);
        messagesEl.scrollTop = messagesEl.scrollHeight;

        return id;
    }

    removeMessage(id) {
        const el = document.getElementById(`msg-${id}`);
        if (el) el.remove();
    }

    formatMessage(text) {
        if (!text) return '';

        // Escape HTML
        let formatted = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Convert markdown-style formatting
        formatted = formatted
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Code blocks
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            // Inline code
            .replace(/`(.*?)`/g, '<code>$1</code>')
            // Line breaks
            .replace(/\n/g, '<br>');

        // Convert lists
        formatted = formatted.replace(/(?:^|\<br\>)- (.*?)(?=\<br\>|$)/g, '<li>$1</li>');
        formatted = formatted.replace(/(<li>.*<\/li>)+/g, '<ul>$&</ul>');

        // Numbered lists
        formatted = formatted.replace(/(?:^|\<br\>)\d+\. (.*?)(?=\<br\>|$)/g, '<li>$1</li>');

        return formatted;
    }

    getCsrfToken() {
        // Try to get CSRF token from cookie or meta tag
        const cookieMatch = document.cookie.match(/csrf_token=([^;]+)/);
        if (cookieMatch) return cookieMatch[1];

        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.content;

        return '';
    }

    clearHistory() {
        fetch(`${this.options.apiBase}/chat/clear`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
        }).then(() => {
            const messagesEl = document.getElementById('ai-messages');
            messagesEl.innerHTML = `
                <div class="ai-message assistant">
                    <div class="ai-message-content">
                        <p>Conversation cleared. How can I help you?</p>
                    </div>
                </div>
            `;
        });
    }
}

// Auto-initialize if container exists
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('ai-chat-container');
    if (container) {
        window.schedulerAI = new SchedulerAIChat('ai-chat-container');
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SchedulerAIChat;
}
