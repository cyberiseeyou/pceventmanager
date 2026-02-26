/**
 * Navigation Manager
 * Handles sidebar toggle, overlay, and keyboard navigation
 */

class NavigationManager {
    constructor() {
        this.hamburgerBtn = document.getElementById('hamburgerBtn');
        this.sidebar = document.getElementById('sidebar');
        this.sidebarOverlay = document.getElementById('sidebarOverlay');
        this.sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
        this.sidebarRefreshBtn = document.getElementById('sidebarRefreshBtn');
        this.isSidebarOpen = false;

        this.init();
    }

    init() {
        // Hamburger menu toggle
        if (this.hamburgerBtn) {
            this.hamburgerBtn.addEventListener('click', () => this.toggleSidebar());
        }

        // Sidebar close button
        if (this.sidebarCloseBtn) {
            this.sidebarCloseBtn.addEventListener('click', () => this.closeSidebar());
        }

        // Overlay click closes sidebar
        if (this.sidebarOverlay) {
            this.sidebarOverlay.addEventListener('click', () => this.closeSidebar());
        }

        // Sidebar refresh database button triggers the same modal
        if (this.sidebarRefreshBtn) {
            this.sidebarRefreshBtn.addEventListener('click', () => {
                this.closeSidebar();
                const refreshBtn = document.getElementById('refreshDatabaseBtn');
                if (refreshBtn) {
                    refreshBtn.click();
                }
            });
        }

        // Close sidebar when clicking a nav link
        if (this.sidebar) {
            this.sidebar.querySelectorAll('a.sidebar-item').forEach(link => {
                link.addEventListener('click', () => {
                    this.closeSidebar();
                });
            });
        }

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isSidebarOpen) {
                this.closeSidebar();
            }
        });
    }

    toggleSidebar() {
        if (this.isSidebarOpen) {
            this.closeSidebar();
        } else {
            this.openSidebar();
        }
    }

    openSidebar() {
        if (this.sidebar) this.sidebar.classList.add('open');
        if (this.sidebarOverlay) this.sidebarOverlay.classList.add('active');
        if (this.hamburgerBtn) {
            this.hamburgerBtn.classList.add('hamburger-menu--open');
            this.hamburgerBtn.setAttribute('aria-expanded', 'true');
        }
        this.isSidebarOpen = true;
        document.body.style.overflow = 'hidden';
    }

    closeSidebar() {
        if (this.sidebar) this.sidebar.classList.remove('open');
        if (this.sidebarOverlay) this.sidebarOverlay.classList.remove('active');
        if (this.hamburgerBtn) {
            this.hamburgerBtn.classList.remove('hamburger-menu--open');
            this.hamburgerBtn.setAttribute('aria-expanded', 'false');
        }
        this.isSidebarOpen = false;
        document.body.style.overflow = '';
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
