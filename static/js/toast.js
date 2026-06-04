(function () {
    var host = null;
    var hideTimer = null;

    function ensureHost() {
        if (host) return host;
        host = document.createElement('div');
        host.className = 'toast-host';
        host.setAttribute('aria-live', 'polite');
        document.body.appendChild(host);
        return host;
    }

    window.showToast = function (message, category) {
        if (!message) return;
        var el = ensureHost();
        el.textContent = message;
        el.className = 'toast-host toast-host--visible';
        if (category === 'warning') el.classList.add('toast-host--warning');
        else if (category === 'error') el.classList.add('toast-host--error');
        else el.classList.remove('toast-host--warning', 'toast-host--error');
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            el.classList.remove('toast-host--visible');
        }, 4500);
    };

    document.addEventListener('DOMContentLoaded', function () {
        var flashes = document.querySelectorAll('[data-flash-message]');
        if (!flashes.length) return;
        var last = flashes[flashes.length - 1];
        showToast(last.getAttribute('data-flash-message'), last.getAttribute('data-flash-category') || '');
        var wrap = document.querySelector('.flash-messages');
        if (wrap) wrap.style.display = 'none';
    });
})();
