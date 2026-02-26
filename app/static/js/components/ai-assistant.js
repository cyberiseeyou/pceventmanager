/**
 * AI Assistant Panel Component
 * 
 * Handles side-panel interaction, context scraping, and unified AI service communication.
 */

class AIAssistantPanel {
    constructor() {
        // UI Elements
        this.panel = document.getElementById('ai-panel');
        this.toggleBtn = document.getElementById('aiPanelToggle');
        this.closeBtn = document.getElementById('ai-panel-close');
        this.overlay = document.getElementById('ai-panel-overlay');
        this.messagesContainer = document.getElementById('ai-messages');
        this.input = document.getElementById('ai-input');
        this.sendBtn = document.getElementById('ai-send-btn');
        this.suggestionsContainer = document.getElementById('ai-suggestions');

        // Context Elements
        this.contextCard = document.getElementById('ai-context-card');
        this.contextDetails = document.getElementById('ai-context-details');

        // State
        this.isOpen = false;
        this.conversationId = null;
        this.conversationHistory = [];
        this.isProcessing = false;

        this.init();
    }

    init() {
        if (!this.panel) {
            console.warn('[AIAssistantPanel] Panel element not found');
            return;
        }

        // Event Listeners
        if (this.toggleBtn) {
            this.toggleBtn.addEventListener('click', () => this.togglePanel());
        } else {
            console.warn('[AIAssistantPanel] Toggle button not found');
        }

        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.closePanel());
        }

        if (this.overlay) {
            this.overlay.addEventListener('click', () => this.closePanel());
        }

        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (this.input) {
            this.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Keyboard Shortcut (Ctrl+K)
        document.addEventListener('keydown', (e) => {
            // Skip shortcuts when user is typing in form fields
            if (e.target.matches('input, textarea, select, [contenteditable]')) return;
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.togglePanel();
            }
        });

        // Load suggestions
        this.loadSuggestions();

        console.log('[AIAssistantPanel] Initialized successfully');
    }

    togglePanel() {
        if (this.isOpen) {
            this.closePanel();
        } else {
            this.openPanel();
        }
    }

    openPanel() {
        this.panel.classList.add('open');
        this.panel.setAttribute('aria-hidden', 'false');
        this.isOpen = true;
        this.input.focus();

        // Refresh context when opening
        this.updateContext();
    }

    closePanel() {
        this.panel.classList.remove('open');
        this.panel.setAttribute('aria-hidden', 'true');
        this.isOpen = false;
    }

    updateContext() {
        const path = window.location.pathname;
        let contextText = "Viewing ";
        let actions = [];

        // Determine context and actions
        if (path.includes('schedule')) {
            // Extract date from URL path (e.g. /schedule/daily/2026-02-21)
            const dateMatch = path.match(/\/(\d{4}-\d{2}-\d{2})/);
            const dateStr = dateMatch ? dateMatch[1] : 'current view';
            contextText += `Schedule for ${dateStr}`;

            actions.push({
                label: 'Verify Schedule',
                query: `verify schedule for ${dateStr}`,
                icon: '✓'
            });
            actions.push({
                label: 'Fill Empty Slots',
                query: `find empty slots in ${dateStr} schedule and suggest employees`,
                icon: '👥'
            });

            this.contextCard.style.display = 'flex';
        } else if (path.includes('employees')) {
            contextText += "Employee List";

            actions.push({
                label: 'Analyze Coverage',
                query: 'analyze employee coverage and role distribution',
                icon: '📊'
            });

            this.contextCard.style.display = 'flex';
        } else {
            this.contextCard.style.display = 'none';
        }

        this.contextDetails.textContent = contextText;

        // Render Context Actions
        const actionsContainer = document.getElementById('ai-context-actions');
        if (actionsContainer) {
            actionsContainer.innerHTML = '';
            actions.forEach(action => {
                const btn = document.createElement('button');
                btn.className = 'btn-xs btn-outline';
                btn.innerHTML = `${action.icon} ${action.label}`;
                btn.onclick = () => {
                    this.input.value = action.query;
                    this.sendMessage();
                };
                actionsContainer.appendChild(btn);
            });
        }

        this.currentContext = {
            url: window.location.href,
            path: path,
            view_name: document.title,
            summary: contextText
        };
    }

    async loadSuggestions() {
        try {
            const response = await fetch('/api/ai/suggestions');
            if (response.ok) {
                const data = await response.json();
                this.renderSuggestions(data.suggestions);
            }
        } catch (error) {
            console.warn('Failed to load AI suggestions', error);
        }
    }

    renderSuggestions(suggestions) {
        this.suggestionsContainer.innerHTML = '';
        suggestions.forEach(suggestion => {
            const chip = document.createElement('button');
            chip.className = 'ai-suggestion-chip';
            chip.textContent = suggestion.label;
            chip.onclick = () => {
                this.input.value = suggestion.query;
                this.sendMessage();
            };
            this.suggestionsContainer.appendChild(chip);
        });
    }

    async sendMessage() {
        const text = this.input.value.trim();
        if (!text || this.isProcessing) return;

        // Clear input
        this.input.value = '';

        // Add User Message
        this.addMessage('user', text);
        this.isProcessing = true;

        // Show loading placeholder
        const loadingId = this.addLoadingIndicator();

        try {
            const response = await fetch('/api/ai/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    query: text,
                    conversation_id: this.conversationId,
                    history: this.conversationHistory,
                    context: this.currentContext
                })
            });

            // Remove loading
            this.removeMessage(loadingId);

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            this.conversationId = data.conversation_id;

            // Add Assistant Response
            this.addMessage('assistant', data.response);

            // Render confirmation buttons if the action requires it
            if (data.requires_confirmation && data.confirmation_data) {
                this.addConfirmationButtons(data.confirmation_data);
            }

            // Update History
            this.conversationHistory.push({ role: 'user', content: text });
            this.conversationHistory.push({ role: 'assistant', content: data.response });

        } catch (error) {
            this.removeMessage(loadingId);
            this.addMessage('assistant', "I'm sorry, I encountered an error. Please try again.");
            console.error('AI Error:', error);
        } finally {
            this.isProcessing = false;
        }
    }

    addConfirmationButtons(confirmationData) {
        const wrapper = document.createElement('div');
        wrapper.className = 'ai-confirmation';
        wrapper.innerHTML = `
            <div class="ai-confirmation-text">${this.formatText(confirmationData.action || 'Proceed with this action?')}</div>
            <div class="ai-confirmation-actions">
                <button class="ai-confirm-btn confirm" data-action="confirm">Confirm</button>
                <button class="ai-confirm-btn cancel" data-action="cancel">Cancel</button>
            </div>
        `;

        wrapper.querySelector('[data-action="confirm"]').addEventListener('click', () => {
            this.confirmAction(confirmationData, wrapper);
        });
        wrapper.querySelector('[data-action="cancel"]').addEventListener('click', () => {
            this.cancelAction(wrapper);
        });

        this.messagesContainer.appendChild(wrapper);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    async confirmAction(confirmationData, buttonWrapper) {
        // Disable buttons to prevent double-click
        buttonWrapper.querySelectorAll('button').forEach(btn => { btn.disabled = true; });

        const loadingId = this.addLoadingIndicator();
        try {
            const response = await fetch('/api/ai/confirm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({ confirmation_data: confirmationData })
            });

            this.removeMessage(loadingId);
            buttonWrapper.remove();

            if (!response.ok) {
                throw new Error('Confirmation request failed');
            }

            const data = await response.json();
            this.addMessage('assistant', data.response);
            this.conversationHistory.push({ role: 'assistant', content: data.response });

        } catch (error) {
            this.removeMessage(loadingId);
            buttonWrapper.remove();
            this.addMessage('assistant', "Failed to execute action. Please try again.");
            console.error('AI Confirm Error:', error);
        }
    }

    cancelAction(buttonWrapper) {
        buttonWrapper.remove();
        this.addMessage('assistant', 'Action cancelled.');
        this.conversationHistory.push({ role: 'assistant', content: 'Action cancelled.' });
    }

    addMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `ai-message ${role}-message`;
        msgDiv.innerHTML = `
            <div class="ai-avatar">${role === 'user' ? '👤' : '🤖'}</div>
            <div class="ai-bubble"><p>${this.formatText(text)}</p></div>
        `;
        this.messagesContainer.appendChild(msgDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    addLoadingIndicator() {
        const id = 'loading-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.id = id;
        msgDiv.className = 'ai-message assistant-message';
        msgDiv.innerHTML = `
            <div class="ai-avatar">🤖</div>
            <div class="ai-bubble"><p>Thinking...</p></div>
        `;
        this.messagesContainer.appendChild(msgDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        return id;
    }

    removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    formatText(text) {
        // Escape HTML first to prevent XSS
        let escaped = String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
        // Then apply markdown formatting
        return escaped
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    getCsrfToken() {
        if (typeof window.getCsrfToken === 'function') {
            return window.getCsrfToken();
        }
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        return metaTag?.content || '';
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.aiPanel = new AIAssistantPanel();
});
