/**
 * AI Assistant Component
 *
 * Handles chat interactions with the AI assistant
 * Supports both cloud API and local Ollama RAG API
 */

class AIAssistant {
    constructor(options = {}) {
        // DOM elements
        this.container = document.getElementById('ai-chat-container');
        this.toggleBtn = document.getElementById('ai-chat-toggle');
        this.closeBtn = document.getElementById('ai-chat-close');
        this.chatWindow = document.getElementById('ai-chat-window');
        this.messagesContainer = document.getElementById('ai-messages');
        this.suggestionsContainer = document.getElementById('ai-suggestions');
        this.suggestionsList = document.getElementById('ai-suggestions-list');
        this.input = document.getElementById('ai-input');
        this.sendBtn = document.getElementById('ai-send-btn');

        // Configuration
        this.options = {
            preferLocal: true,  // Prefer local Ollama RAG API if available
            cloudApiBase: '/api/ai',
            ragApiBase: '/api/ai/rag',
            ...options
        };

        // State
        this.isOpen = false;
        this.conversationId = null;
        this.conversationHistory = [];
        this.pendingConfirmation = null;
        this.useRagApi = false;  // Will be set based on health check
        this.providerInfo = null;

        this.init();
    }

    init() {
        // Event listeners
        this.toggleBtn.addEventListener('click', () => this.toggleChat());
        this.closeBtn.addEventListener('click', () => this.closeChat());
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keydown', (e) => this.handleInputKeydown(e));

        // Auto-resize textarea
        this.input.addEventListener('input', () => this.autoResizeInput());

        // Keyboard shortcut (Ctrl+K or Cmd+K)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.toggleChat();
            }
        });

        // Load suggestions
        this.loadSuggestions();

        // Check AI health
        this.checkHealth();
    }

    toggleChat() {
        if (this.isOpen) {
            this.closeChat();
        } else {
            this.openChat();
        }
    }

    openChat() {
        this.chatWindow.style.display = 'flex';
        this.isOpen = true;
        this.input.focus();

        // Show/hide suggestions based on messages
        if (this.conversationHistory.length === 0) {
            this.suggestionsContainer.style.display = 'block';
        } else {
            this.suggestionsContainer.style.display = 'none';
        }
    }

    closeChat() {
        this.chatWindow.style.display = 'none';
        this.isOpen = false;
    }

    async loadSuggestions() {
        try {
            const response = await fetch('/api/ai/suggestions');
            if (!response.ok) return;

            const data = await response.json();
            this.renderSuggestions(data.suggestions);
        } catch (error) {
            console.error('Failed to load suggestions:', error);
        }
    }

    renderSuggestions(suggestions) {
        this.suggestionsList.innerHTML = '';

        suggestions.forEach(suggestion => {
            const chip = document.createElement('div');
            chip.className = 'ai-suggestion-chip';
            chip.innerHTML = `
                <span class="ai-suggestion-icon">${suggestion.icon}</span>
                <span>${suggestion.label}</span>
            `;
            chip.addEventListener('click', () => {
                this.input.value = suggestion.query;
                this.sendMessage();
            });
            this.suggestionsList.appendChild(chip);
        });
    }

    handleInputKeydown(e) {
        // Send on Enter (without Shift)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendMessage();
        }
    }

    autoResizeInput() {
        this.input.style.height = 'auto';
        this.input.style.height = this.input.scrollHeight + 'px';
    }

    async sendMessage() {
        const message = this.input.value.trim();
        if (!message) return;

        // Clear input
        this.input.value = '';
        this.autoResizeInput();

        // Hide suggestions
        this.suggestionsContainer.style.display = 'none';

        // Add user message to chat
        this.addMessage('user', message);

        // Show loading indicator
        const loadingId = this.showLoading();

        try {
            let response, data;

            if (this.useRagApi) {
                // Use local RAG API (Ollama)
                response = await fetch(`${this.options.ragApiBase}/chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to get response');
                }

                data = await response.json();

                // Remove loading
                this.removeLoading(loadingId);

                // Update conversation history
                this.conversationHistory.push(
                    { role: 'user', content: message },
                    { role: 'assistant', content: data.answer }
                );

                // Add assistant response
                this.addMessage('assistant', data.answer, {
                    response: data.answer,
                    metadata: data.metadata
                });

            } else {
                // Use cloud API
                response = await fetch(`${this.options.cloudApiBase}/query`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: message,
                        conversation_id: this.conversationId,
                        history: this.conversationHistory
                    })
                });

                // Remove loading
                this.removeLoading(loadingId);

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to get response');
                }

                data = await response.json();

                // Update conversation
                this.conversationId = data.conversation_id;
                this.conversationHistory.push(
                    { role: 'user', content: message },
                    { role: 'assistant', content: data.response }
                );

                // Add assistant response
                this.addMessage('assistant', data.response, data);
            }

        } catch (error) {
            console.error('Error sending message:', error);
            this.removeLoading(loadingId);
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}`);
        }
    }

    addMessage(role, content, data = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `ai-message ${role}-message`;

        const avatar = document.createElement('div');
        avatar.className = `ai-message-avatar ${role}-avatar`;
        avatar.textContent = role === 'user' ? '👤' : '🤖';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'ai-message-content';

        const bubble = document.createElement('div');
        bubble.className = 'ai-message-bubble';
        bubble.textContent = content;

        contentDiv.appendChild(bubble);

        // Add actions if present
        if (data && data.actions) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'ai-message-actions';

            data.actions.forEach(action => {
                const btn = document.createElement('button');
                btn.className = 'ai-action-btn';
                btn.textContent = action.label;
                btn.addEventListener('click', () => {
                    if (action.action.startsWith('/')) {
                        window.location.href = action.action;
                    }
                });
                actionsDiv.appendChild(btn);
            });

            contentDiv.appendChild(actionsDiv);
        }

        // Add confirmation if required
        if (data && data.requires_confirmation) {
            const confirmDiv = this.createConfirmationUI(data.confirmation_data);
            contentDiv.appendChild(confirmDiv);
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    createConfirmationUI(confirmationData) {
        const confirmDiv = document.createElement('div');
        confirmDiv.className = 'ai-confirmation';

        const text = document.createElement('div');
        text.className = 'ai-confirmation-text';
        text.textContent = 'Do you want to proceed?';

        const actions = document.createElement('div');
        actions.className = 'ai-confirmation-actions';

        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'ai-confirm-btn confirm';
        confirmBtn.textContent = 'Confirm';
        confirmBtn.addEventListener('click', () => this.confirmAction(confirmationData, confirmDiv));

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'ai-confirm-btn cancel';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', () => {
            confirmDiv.remove();
            this.addMessage('assistant', 'Action cancelled.');
        });

        actions.appendChild(confirmBtn);
        actions.appendChild(cancelBtn);

        confirmDiv.appendChild(text);
        confirmDiv.appendChild(actions);

        return confirmDiv;
    }

    async confirmAction(confirmationData, confirmDiv) {
        // Disable buttons
        const buttons = confirmDiv.querySelectorAll('button');
        buttons.forEach(btn => btn.disabled = true);

        try {
            const response = await fetch('/api/ai/confirm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    confirmation_data: confirmationData
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to confirm action');
            }

            const data = await response.json();

            // Remove confirmation UI
            confirmDiv.remove();

            // Add result message
            this.addMessage('assistant', data.response, data);

        } catch (error) {
            console.error('Error confirming action:', error);
            confirmDiv.remove();
            this.addMessage('assistant', `Error: ${error.message}`);
        }
    }

    showLoading() {
        const loadingId = `loading-${Date.now()}`;
        const loadingDiv = document.createElement('div');
        loadingDiv.id = loadingId;
        loadingDiv.className = 'ai-message assistant-message';

        const avatar = document.createElement('div');
        avatar.className = 'ai-message-avatar bot-avatar';
        avatar.textContent = '🤖';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'ai-message-content';

        const bubble = document.createElement('div');
        bubble.className = 'ai-message-bubble';

        const loading = document.createElement('div');
        loading.className = 'ai-loading';
        loading.innerHTML = `
            <div class="ai-loading-dot"></div>
            <div class="ai-loading-dot"></div>
            <div class="ai-loading-dot"></div>
        `;

        bubble.appendChild(loading);
        contentDiv.appendChild(bubble);
        loadingDiv.appendChild(avatar);
        loadingDiv.appendChild(contentDiv);

        this.messagesContainer.appendChild(loadingDiv);
        this.scrollToBottom();

        return loadingId;
    }

    removeLoading(loadingId) {
        const loadingDiv = document.getElementById(loadingId);
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    async checkHealth() {
        // First, check if local RAG API (Ollama) is available
        if (this.options.preferLocal) {
            try {
                const ragResponse = await fetch(`${this.options.ragApiBase}/health`);
                const ragData = await ragResponse.json();

                if (ragData.status === 'healthy') {
                    this.useRagApi = true;
                    this.providerInfo = {
                        type: 'local',
                        provider: ragData.providers?.primary?.provider || 'ollama',
                        model: ragData.config?.model || 'ministral-3:3b'
                    };
                    console.log('AI Assistant: Using local Ollama RAG API', this.providerInfo);
                    this.updateProviderIndicator();
                    return;
                }
            } catch (error) {
                console.log('Local RAG API not available, trying cloud API...');
            }
        }

        // Fall back to cloud API
        try {
            const response = await fetch(`${this.options.cloudApiBase}/health`);
            const data = await response.json();

            if (data.status === 'ok' && data.configured) {
                this.useRagApi = false;
                this.providerInfo = {
                    type: 'cloud',
                    provider: data.provider || 'unknown'
                };
                console.log('AI Assistant: Using cloud API', this.providerInfo);
                this.updateProviderIndicator();
            } else {
                console.warn('AI Assistant not configured:', data.message);
                this.providerInfo = { type: 'none', error: data.message };
                this.updateProviderIndicator();
            }
        } catch (error) {
            console.error('Failed to check AI health:', error);
            this.providerInfo = { type: 'none', error: error.message };
            this.updateProviderIndicator();
        }
    }

    updateProviderIndicator() {
        // Update the header subtitle to show which provider is being used
        const subtitle = this.chatWindow?.querySelector('.ai-header-subtitle');
        if (subtitle && this.providerInfo) {
            if (this.providerInfo.type === 'local') {
                subtitle.textContent = `Local AI (${this.providerInfo.model})`;
                subtitle.style.color = '#90EE90';  // Light green
            } else if (this.providerInfo.type === 'cloud') {
                subtitle.textContent = `Cloud AI (${this.providerInfo.provider})`;
                subtitle.style.color = '#87CEEB';  // Light blue
            } else {
                subtitle.textContent = 'AI not configured';
                subtitle.style.color = '#FFB6C1';  // Light red
            }
        }
    }

    getApiEndpoint() {
        return this.useRagApi ? this.options.ragApiBase : this.options.cloudApiBase;
    }
}
