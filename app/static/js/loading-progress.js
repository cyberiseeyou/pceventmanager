/**
 * Loading Progress Manager
 * Handles SSE connection and UI updates for database refresh progress
 */
class LoadingProgressManager {
    constructor(config) {
        this.taskId = config.taskId;
        this.redirectUrl = config.redirectUrl;
        this.eventSource = null;

        // DOM elements
        this.progressBar = document.getElementById('progressBar');
        this.progressPercentage = document.getElementById('progressPercentage');
        this.currentStepText = document.getElementById('currentStepText');
        this.currentStepDetail = document.getElementById('currentStepDetail');
        this.errorContainer = document.getElementById('errorContainer');
        this.errorMessage = document.getElementById('errorMessage');
        this.retryButton = document.getElementById('retryButton');

        this.init();
    }

    init() {
        // Bind retry button
        if (this.retryButton) {
            this.retryButton.addEventListener('click', () => this.handleRetry());
        }

        // Start the refresh process
        this.startRefresh();

        // Connect to SSE for progress updates
        this.connectSSE();
    }

    async startRefresh() {
        try {
            const response = await fetch(`/loading/start/${this.taskId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                const data = await response.json();
                console.error('Failed to start refresh:', data.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Failed to start refresh:', error);
        }
    }

    connectSSE() {
        this.eventSource = new EventSource(`/loading/progress/${this.taskId}`);

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.updateUI(data);

                if (data.status === 'completed') {
                    this.handleCompletion(data);
                } else if (data.status === 'error') {
                    this.handleError(data);
                }
            } catch (error) {
                console.error('Error parsing SSE data:', error);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);
            this.eventSource.close();

            // Show error after a brief delay to allow for normal completion
            setTimeout(() => {
                if (!this.isCompleted) {
                    this.handleError({ error: 'Connection lost. Please refresh the page.' });
                }
            }, 2000);
        };
    }

    updateUI(data) {
        // Calculate and update progress bar
        const currentStep = data.current_step || 0;
        const totalSteps = data.total_steps || 5;

        // Calculate percentage based on step progress
        let percentage = 0;
        if (currentStep > 0) {
            // Base percentage from completed steps
            const stepWeight = 100 / totalSteps;
            percentage = Math.min(100, (currentStep - 1) * stepWeight);

            // Add partial progress within current step (for step 3 - processing)
            if (currentStep === 3 && data.total > 0 && data.processed > 0) {
                const stepProgress = (data.processed / data.total) * stepWeight;
                percentage += stepProgress;
            } else if (currentStep > 0) {
                // For other active steps, add half the step weight
                percentage += stepWeight * 0.5;
            }
        }

        // On completion, set to 100%
        if (data.status === 'completed') {
            percentage = 100;
        }

        this.progressBar.style.width = `${Math.round(percentage)}%`;
        this.progressPercentage.textContent = `${Math.round(percentage)}%`;

        // Update current step text
        this.currentStepText.textContent = data.step_label || 'Processing...';

        // Show processing count for step 3
        if (data.current_step === 3 && data.total > 0) {
            const processed = data.processed || 0;
            this.currentStepDetail.textContent =
                `${processed.toLocaleString()} of ${data.total.toLocaleString()} events`;
            this.currentStepDetail.style.display = 'block';
        } else {
            this.currentStepDetail.style.display = 'none';
        }
    }

    handleCompletion(data) {
        this.isCompleted = true;
        this.eventSource.close();

        // Mark complete
        this.progressBar.style.width = '100%';
        this.progressPercentage.textContent = '100%';
        this.currentStepText.textContent = 'Database updated successfully!';
        this.currentStepDetail.style.display = 'none';

        // Add success class to progress section
        const progressSection = document.querySelector('.loading-progress-section');
        if (progressSection) {
            progressSection.classList.add('success');
        }

        // Update footer message
        const footer = document.querySelector('.loading-footer p');
        if (footer) {
            footer.textContent = 'Database updated successfully! Redirecting...';
        }

        // Show stats if available
        if (data.stats) {
            console.log('Refresh stats:', data.stats);
        }

        // Redirect after a short delay
        setTimeout(() => {
            window.location.href = this.redirectUrl;
        }, 1500);
    }

    handleError(data) {
        this.eventSource.close();

        // Update current step text to show error
        this.currentStepText.textContent = 'Database refresh failed';
        this.currentStepDetail.style.display = 'none';

        // Update footer
        const footer = document.querySelector('.loading-footer p');
        if (footer) {
            footer.textContent = 'An error occurred during database refresh.';
        }

        // Show error container
        if (this.errorContainer) {
            this.errorContainer.style.display = 'block';
            if (data.error && this.errorMessage) {
                this.errorMessage.textContent = data.error;
            }
        }

        // Stop shimmer animation
        const shimmer = document.querySelector('.progress-bar-shimmer');
        if (shimmer) {
            shimmer.style.animation = 'none';
        }
    }

    handleRetry() {
        // Reload the page to start fresh
        window.location.reload();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (window.LOADING_CONFIG) {
        new LoadingProgressManager(window.LOADING_CONFIG);
    } else {
        console.error('Loading configuration not found');
    }
});
