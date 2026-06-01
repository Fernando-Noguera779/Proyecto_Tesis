(function() {
    'use strict';
    var toggleBtn = document.getElementById('sidebarToggle');
    var sidebar = document.querySelector('.navbar-institutional');
    var overlay = document.getElementById('sidebarOverlay');
    if (!toggleBtn || !sidebar || !overlay) return;

    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    toggleBtn.addEventListener('click', function() {
        var isOpen = sidebar.classList.contains('open');
        if (isOpen) { closeSidebar(); }
        else {
            sidebar.classList.add('open');
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    });
    overlay.addEventListener('click', closeSidebar);
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeSidebar();
    });
    window.addEventListener('resize', function() {
        if (window.innerWidth > 768) closeSidebar();
    });
})();
