/**
 * User Profile Dropdown Component
 * Handles dropdown menu interactions for user profile in header
 */

(function() {
    'use strict';

    // Wait for DOM to be ready
    document.addEventListener('DOMContentLoaded', function() {
        const dropdownToggle = document.getElementById('userDropdownToggle');
        const dropdownMenu = document.getElementById('userDropdownMenu');

        if (!dropdownToggle || !dropdownMenu) {
            console.warn('User dropdown elements not found');
            return;
        }

        /**
         * Toggle dropdown open/close
         */
        function toggleDropdown(event) {
            event.preventDefault();
            event.stopPropagation();

            const isHidden = dropdownMenu.hasAttribute('hidden');

            if (isHidden) {
                openDropdown();
            } else {
                closeDropdown();
            }
        }

        /**
         * Open dropdown menu
         */
        function openDropdown() {
            dropdownMenu.removeAttribute('hidden');
            dropdownToggle.setAttribute('aria-expanded', 'true');
            dropdownMenu.classList.add('active');
        }

        /**
         * Close dropdown menu
         */
        function closeDropdown() {
            dropdownMenu.setAttribute('hidden', '');
            dropdownToggle.setAttribute('aria-expanded', 'false');
            dropdownMenu.classList.remove('active');
        }

        /**
         * Close dropdown when clicking outside
         */
        function handleClickOutside(event) {
            const userDropdown = dropdownToggle.closest('.user-dropdown');

            if (userDropdown && !userDropdown.contains(event.target)) {
                closeDropdown();
            }
        }

        /**
         * Handle keyboard navigation
         */
        function handleKeydown(event) {
            // Close on Escape key
            if (event.key === 'Escape' || event.key === 'Esc') {
                closeDropdown();
                dropdownToggle.focus();
            }

            // Open/close on Enter or Space
            if (event.target === dropdownToggle && (event.key === 'Enter' || event.key === ' ')) {
                event.preventDefault();
                toggleDropdown(event);
            }

            // Navigate menu items with arrow keys when dropdown is open
            if (!dropdownMenu.hasAttribute('hidden')) {
                const menuItems = Array.from(dropdownMenu.querySelectorAll('.dropdown-item'));

                if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    const currentIndex = menuItems.indexOf(document.activeElement);
                    const nextIndex = currentIndex < menuItems.length - 1 ? currentIndex + 1 : 0;
                    menuItems[nextIndex].focus();
                }

                if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    const currentIndex = menuItems.indexOf(document.activeElement);
                    const prevIndex = currentIndex > 0 ? currentIndex - 1 : menuItems.length - 1;
                    menuItems[prevIndex].focus();
                }
            }
        }

        // Event listeners
        dropdownToggle.addEventListener('click', toggleDropdown);
        document.addEventListener('click', handleClickOutside);
        document.addEventListener('keydown', handleKeydown);

        // Cleanup on page unload
        window.addEventListener('beforeunload', function() {
            dropdownToggle.removeEventListener('click', toggleDropdown);
            document.removeEventListener('click', handleClickOutside);
            document.removeEventListener('keydown', handleKeydown);
        });
    });
})();
