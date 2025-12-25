/**
 * Dashboard Page JavaScript
 *
 * Handles Schedule Now button clicks on unscheduled event cards.
 * Opens ScheduleModal component from Epic 2 Story 2.1.
 *
 * Epic 2, Story 2.2: Add Schedule Now Buttons to Dashboard
 */

import { ScheduleModal } from '../components/schedule-modal.js';

/**
 * Initialize dashboard functionality when DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log('[Dashboard] Initializing dashboard page handlers');

  // Use event delegation for dynamically added Schedule Now buttons
  document.body.addEventListener('click', (e) => {
    const button = e.target.closest('.schedule-now-btn');
    if (button) {
      console.log('[Dashboard] Schedule Now button clicked');
      handleScheduleNowClick(button);
    }
  });

  console.log('[Dashboard] Dashboard page initialized');
});

/**
 * Handle Schedule Now button click
 * Extracts event data from button attributes and opens ScheduleModal
 *
 * @param {HTMLButtonElement} button - The clicked Schedule Now button
 */
function handleScheduleNowClick(button) {
  console.log('[Dashboard] handleScheduleNowClick called');

  // Show loading state on button
  setButtonLoading(button, true);

  try {
    // Extract event data from data-* attributes
    const eventData = {
      event_id: parseInt(button.dataset.eventId),
      event_name: button.dataset.eventName,
      event_type: button.dataset.eventType,
      location: button.dataset.location || '',
      duration: parseInt(button.dataset.duration) || 120,
      date_needed: button.dataset.dateNeeded
    };

    console.log('[Dashboard] Event data extracted:', eventData);

    // Validate required fields
    if (!eventData.event_id || !eventData.event_name || !eventData.event_type) {
      console.error('[Dashboard] Missing required event data:', eventData);
      alert('Error: Missing event information. Please refresh the page and try again.');
      setButtonLoading(button, false);
      return;
    }

    // Open the schedule modal with event context
    const modal = new ScheduleModal(eventData);
    modal.render();

    console.log('[Dashboard] ScheduleModal opened successfully');

    // Listen for modal close to reset button state
    // Use a named function so we can properly clean up the listener
    const handleModalClosed = (event) => {
      console.log('[Dashboard] Modal closed event received:', event.detail);

      // Check if this is the modal we opened (by matching event ID in modal ID)
      if (event.detail && event.detail.id === `schedule-modal-${eventData.event_id}`) {
        setButtonLoading(button, false);
        document.removeEventListener('modal-closed', handleModalClosed);
      }
    };

    document.addEventListener('modal-closed', handleModalClosed);

  } catch (error) {
    console.error('[Dashboard] Error opening schedule modal:', error);
    alert('Error opening schedule modal. Please try again.');
    setButtonLoading(button, false);
  }
}

/**
 * Set button loading state
 * Shows spinner and disables button when loading
 *
 * @param {HTMLButtonElement} button - The button to update
 * @param {boolean} isLoading - Whether button should show loading state
 */
function setButtonLoading(button, isLoading) {
  const btnText = button.querySelector('.btn-text');
  const btnSpinner = button.querySelector('.btn-spinner');

  if (!btnText || !btnSpinner) {
    console.warn('[Dashboard] Button text or spinner not found in button');
    return;
  }

  if (isLoading) {
    button.disabled = true;
    btnText.style.display = 'none';
    btnSpinner.style.display = 'inline';
  } else {
    button.disabled = false;
    btnText.style.display = 'inline';
    btnSpinner.style.display = 'none';
  }
}
