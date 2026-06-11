(function() {
    var modal = null;
    var timerInterval = null;
    var warningShown = false;

    function actualizarReloj(segundos) {
        var m = Math.floor(segundos / 60);
        var s = segundos % 60;
        var txt = m + ':' + (s < 10 ? '0' : '') + s;
        var el = document.getElementById('sessionTimerDisplay');
        if (el) el.textContent = txt;
        var bar = document.getElementById('sessionTimerBar');
        if (bar) {
            var total = parseInt(bar.getAttribute('data-total') || 1200, 10);
            var pct = Math.min(100, (segundos / total) * 100);
            bar.style.width = pct + '%';
            bar.setAttribute('aria-valuenow', pct);
            if (pct < 20) bar.className = 'progress-bar bg-danger';
            else if (pct < 40) bar.className = 'progress-bar bg-warning';
            else bar.className = 'progress-bar bg-success';
        }
    }

    function mostrarModal() {
        if (warningShown) return;
        warningShown = true;
        var m = document.getElementById('sessionExpiryModal');
        if (m) {
            var bsModal = new bootstrap.Modal(m, { backdrop: 'static', keyboard: false });
            bsModal.show();
            modal = bsModal;
        }
    }

    function ocultarModal() {
        if (modal) {
            modal.hide();
            modal = null;
        }
        warningShown = false;
    }

    function extenderSesion() {
        fetch('/extender-sesion', { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.ok) {
                    ocultarModal();
                    actualizarReloj(data.remaining);
                } else {
                    window.location.href = '/logout';
                }
            })
            .catch(function() { window.location.href = '/logout'; });
    }

    function checkSession() {
        fetch('/tiempo-sesion')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.ok) {
                    window.location.href = '/logout';
                    return;
                }
                var rem = data.remaining;
                actualizarReloj(rem);
                if (rem <= 0) {
                    window.location.href = '/logout';
                } else if (rem <= 60 && !warningShown) {
                    mostrarModal();
                }
            })
            .catch(function() {});
    }

    function iniciar() {
        if (document.getElementById('sessionExpiryModal')) {
            checkSession();
            timerInterval = setInterval(checkSession, 5000);
            document.getElementById('btnExtenderSesion').addEventListener('click', extenderSesion);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
