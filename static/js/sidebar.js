(function () {
    'use strict';

    var sidebar = document.querySelector('.navbar-institutional');
    var toggleBtn = document.getElementById('sidebarToggle');
    var overlay = document.getElementById('sidebarOverlay');
    var mainContent = document.querySelector('.main-content');
    var pinBtn = document.getElementById('sidebarPinBtn');

    if (!sidebar) return;

    // ── Mobile toggle ──
    function openSidebar() {
        sidebar.classList.add('open');
        if (overlay) overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function () {
            if (sidebar.classList.contains('open')) { closeSidebar(); }
            else { openSidebar(); }
        });
    }
    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeSidebar();
    });

    // ── Desktop pin/unpin ──
    var STORAGE_KEY = 'sidebar_pinned';

    function applyPinState(pinned) {
        if (window.innerWidth <= 768) {
            sidebar.classList.remove('collapsed');
            if (mainContent) mainContent.classList.remove('sidebar-collapsed');
            if (pinBtn) {
                pinBtn.classList.remove('pinned');
                pinBtn.title = 'Anclar sidebar';
            }
            return;
        }
        if (!pinned) {
            sidebar.classList.add('collapsed');
            if (mainContent) mainContent.classList.add('sidebar-collapsed');
            if (pinBtn) {
                pinBtn.classList.remove('pinned');
                pinBtn.title = 'Anclar sidebar';
            }
        } else {
            sidebar.classList.remove('collapsed');
            if (mainContent) mainContent.classList.remove('sidebar-collapsed');
            if (pinBtn) {
                pinBtn.classList.add('pinned');
                pinBtn.title = 'Desanclar sidebar';
            }
        }
    }

    // Restore saved state
    var saved = localStorage.getItem(STORAGE_KEY);
    var isPinned = saved === null ? true : saved === 'true';
    applyPinState(isPinned);

    if (pinBtn) {
        pinBtn.addEventListener('click', function () {
            var nowPinned = !sidebar.classList.contains('collapsed');
            localStorage.setItem(STORAGE_KEY, nowPinned);
            applyPinState(nowPinned);
        });
    }

    // On resize, re-apply
    window.addEventListener('resize', function () {
        if (window.innerWidth > 768) closeSidebar();
        var saved2 = localStorage.getItem(STORAGE_KEY);
        applyPinState(saved2 === null ? true : saved2 === 'true');
    });

    // ── On desktop, sidebar expands on hover when unpinned ──
    if (pinBtn) {
        sidebar.addEventListener('mouseenter', function () {
            if (window.innerWidth <= 768) return;
            var pinned = localStorage.getItem(STORAGE_KEY);
            if (pinned === 'false' || pinned === null) {
                sidebar.classList.remove('collapsed');
                if (mainContent) mainContent.classList.remove('sidebar-collapsed');
            }
        });
        sidebar.addEventListener('mouseleave', function () {
            if (window.innerWidth <= 768) return;
            var pinned = localStorage.getItem(STORAGE_KEY);
            if (pinned === 'false' || pinned === null) {
                sidebar.classList.add('collapsed');
                if (mainContent) mainContent.classList.add('sidebar-collapsed');
            }
        });
    }
})();
