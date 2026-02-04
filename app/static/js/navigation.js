/**
 * Navigation Manager
 * Handles dropdown menus and mobile hamburger menu
 */

class NavigationManager {
    constructor() {
        this.hamburgerBtn = document.getElementById('hamburgerBtn');
        this.navLinks = document.getElementById('navLinks');
        this.navDropdowns = document.querySelectorAll('.nav-dropdown');
        this.isMobileMenuOpen = false;

        this.init();
    }

    init() {
        // Hamburger menu toggle
        if (this.hamburgerBtn) {
            this.hamburgerBtn.addEventListener('click', () => this.toggleMobileMenu());
        }

        // Mobile nav close button (FLAW-014)
        const navCloseBtn = document.getElementById('navCloseBtn');
        if (navCloseBtn) {
            navCloseBtn.addEventListener('click', () => this.closeMobileMenu());
        }

        // Desktop dropdown toggles - click only (no hover)
        this.navDropdowns.forEach(dropdown => {
            const toggle = dropdown.querySelector('.nav-dropdown-toggle');
            const menu = dropdown.querySelector('.nav-dropdown-menu');

            // Click to toggle (no hover - click only)
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleDropdown(dropdown);
            });
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.nav-dropdown')) {
                this.closeAllDropdowns();
            }
        });

        // Close mobile menu when clicking nav link
        const navLinksElements = document.querySelectorAll('.nav-link:not(.nav-dropdown-toggle), .nav-dropdown-item');
        navLinksElements.forEach(link => {
            link.addEventListener('click', () => {
                if (this.isMobileMenuOpen) {
                    this.closeMobileMenu();
                }
            });
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768 && this.isMobileMenuOpen) {
                this.closeMobileMenu();
            }
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeAllDropdowns();
                if (this.isMobileMenuOpen) {
                    this.closeMobileMenu();
                }
            }
        });
    }

    toggleMobileMenu() {
        if (this.isMobileMenuOpen) {
            this.closeMobileMenu();
        } else {
            this.openMobileMenu();
        }
    }

    openMobileMenu() {
        this.navLinks.classList.add('nav-links--open');
        this.hamburgerBtn.classList.add('hamburger-menu--open');
        this.hamburgerBtn.setAttribute('aria-expanded', 'true');
        this.isMobileMenuOpen = true;

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    }

    closeMobileMenu() {
        this.navLinks.classList.remove('nav-links--open');
        this.hamburgerBtn.classList.remove('hamburger-menu--open');
        this.hamburgerBtn.setAttribute('aria-expanded', 'false');
        this.isMobileMenuOpen = false;

        // Restore body scroll
        document.body.style.overflow = '';

        // Close all dropdowns
        this.closeAllDropdowns();
    }

    toggleDropdown(dropdown) {
        const isOpen = dropdown.classList.contains('nav-dropdown--open');

        // Close all other dropdowns
        this.closeAllDropdowns();

        // Toggle this dropdown
        if (!isOpen) {
            this.openDropdown(dropdown);
        }
    }

    openDropdown(dropdown) {
        dropdown.classList.add('nav-dropdown--open');
        const toggle = dropdown.querySelector('.nav-dropdown-toggle');
        const menu = dropdown.querySelector('.nav-dropdown-menu');

        toggle.setAttribute('aria-expanded', 'true');
        menu.hidden = false;
    }

    closeDropdown(dropdown) {
        dropdown.classList.remove('nav-dropdown--open');
        const toggle = dropdown.querySelector('.nav-dropdown-toggle');
        const menu = dropdown.querySelector('.nav-dropdown-menu');

        toggle.setAttribute('aria-expanded', 'false');
        menu.hidden = true;
    }

    closeAllDropdowns() {
        this.navDropdowns.forEach(dropdown => {
            this.closeDropdown(dropdown);
        });
    }
}

// Initialize navigation when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.navigationManager = new NavigationManager();
    });
} else {
    window.navigationManager = new NavigationManager();
}
