(function () {
    var btn = document.getElementById('accessGenerateQrBtn');
    var block = document.getElementById('accessQrBlock');
    var img = document.getElementById('accessQrImg');
    var timerEl = document.getElementById('accessQrTimer');
    var ringProgress = document.getElementById('accessTimerRingProgress');
    if (!btn || !block || !img) return;

    var countdownTimer = null;
    var refreshTimer = null;
    var expiresAt = null;
    var totalSeconds = 60;
    var ringLen = 326.7;

    if (ringProgress) {
        ringLen = 2 * Math.PI * 56;
        ringProgress.setAttribute('stroke-dasharray', String(ringLen));
    }

    function pad(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function updateRing(left, total) {
        if (!ringProgress || !total) return;
        var ratio = Math.max(0, left / total);
        ringProgress.setAttribute('stroke-dashoffset', String(ringLen * (1 - ratio)));
        ringProgress.style.stroke = left <= 10 && left > 0
            ? 'var(--access-danger)'
            : 'var(--access-accent)';
    }

    function updateCountdown() {
        if (!expiresAt || !timerEl) return;
        var now = Date.now();
        var left = Math.max(0, Math.floor((expiresAt - now) / 1000));
        var m = Math.floor(left / 60);
        var s = left % 60;
        timerEl.textContent = pad(m) + ':' + pad(s);
        timerEl.classList.toggle('is-warning', left > 0 && left <= 10);
        timerEl.classList.toggle('is-expired', left <= 0);
        updateRing(left, totalSeconds);
        if (left === 0) {
            clearInterval(countdownTimer);
            countdownTimer = null;
        }
        if (left > 0 && left <= 10 && !refreshTimer) {
            refreshTimer = setTimeout(function () {
                refreshTimer = null;
                loadQr(true);
            }, 0);
        }
    }

    function loadQr(silent) {
        if (!silent) {
            btn.disabled = true;
            btn.textContent = 'Генерация…';
        }
        return fetch('/api/my-qr-token')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok || !d.qr_url) {
                    if (!silent) btn.textContent = 'Сгенерировать QR-код';
                    return;
                }
                img.src = d.qr_url + (d.qr_url.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now();
                img.className = 'access-qr-img';
                block.classList.add('is-visible');
                btn.textContent = 'Обновить QR-код';
                expiresAt = d.expires_at ? new Date(d.expires_at).getTime() : Date.now() + 60000;
                totalSeconds = Math.max(1, Math.round((expiresAt - Date.now()) / 1000));
                if (countdownTimer) clearInterval(countdownTimer);
                updateCountdown();
                countdownTimer = setInterval(updateCountdown, 1000);
            })
            .catch(function () {
                if (!silent) btn.textContent = 'Сгенерировать QR-код';
            })
            .finally(function () {
                btn.disabled = false;
            });
    }

    btn.addEventListener('click', function () {
        loadQr(false);
    });
})();
