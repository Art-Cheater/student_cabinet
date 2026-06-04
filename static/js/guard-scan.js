(function () {
    var resultEl = document.getElementById('guardResult');
    var statusEl = document.getElementById('cameraStatus');
    var startBtn = document.getElementById('startCameraBtn');
    var stopBtn = document.getElementById('stopCameraBtn');
    var scanAgainBtn = document.getElementById('scanAgainBtn');
    var readerEl = document.getElementById('qr-reader');
    var scanner = null;
    var scanningLock = false;
    var cameraOn = false;

    function setStatus(text) {
        if (statusEl) statusEl.textContent = text;
    }

    function parseToken(text) {
        var t = (text || '').trim();
        if (!t) return '';
        try {
            var u = new URL(t);
            var parts = u.pathname.split('/').filter(Boolean);
            var gi = parts.indexOf('gate');
            if (gi >= 0 && parts[gi + 1]) return parts[gi + 1];
        } catch (e) { /* plain uuid or path */ }
        if (t.indexOf('/gate/') !== -1) {
            var seg = t.split('/gate/')[1];
            return (seg || '').split(/[?#]/)[0];
        }
        return t;
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function showResult(data, isError) {
        if (!resultEl) return;
        resultEl.hidden = false;
        resultEl.className = 'guard-result ' + (isError ? 'guard-result--error' : 'guard-result--ok');
        if (scanAgainBtn) scanAgainBtn.hidden = false;
        if (isError) {
            resultEl.innerHTML = '<p><strong>Отказ</strong></p><p>' + escapeHtml(data.error || 'Ошибка') + '</p>';
            if (navigator.vibrate) navigator.vibrate(200);
            return;
        }
        var html = '<p><strong>Допуск разрешён</strong></p>';
        html += '<p class="guard-result-fio">' + escapeHtml(data.fio || '') + '</p>';
        if (data.subject_type === 'student' && data.group) {
            html += '<p>Группа: ' + escapeHtml(data.group) + '</p>';
        }
        if (data.position_title) html += '<p>Должность: ' + escapeHtml(data.position_title) + '</p>';
        if (data.department) html += '<p>Подразделение: ' + escapeHtml(data.department) + '</p>';
        if (data.pass_number) html += '<p>№ удостоверения: ' + escapeHtml(data.pass_number) + '</p>';
        if (data.photo_url) {
            html += '<img src="' + escapeHtml(data.photo_url) + '" alt="Фото" class="guard-result-photo">';
        }
        html += '<p class="hint">Действует до: ' + escapeHtml(data.valid_until || '—') + '</p>';
        resultEl.innerHTML = html;
        if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
    }

    async function verify(raw) {
        var token = parseToken(raw);
        if (!token) {
            showResult({ error: 'Не удалось прочитать код' }, true);
            return;
        }
        setStatus('Проверка…');
        try {
            var r = await fetch('/api/guard/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ token: token }),
            });
            var data = await r.json();
            if (data.ok) {
                showResult(data, false);
                setStatus('Пропуск подтверждён');
            } else {
                showResult(data, true);
                setStatus('Пропуск не принят');
            }
        } catch (e) {
            showResult({ error: 'Нет связи с сервером' }, true);
            setStatus('Ошибка сети');
        }
    }

    function onScanSuccess(decodedText) {
        if (scanningLock || !decodedText) return;
        scanningLock = true;
        verify(decodedText).finally(function () {
            setTimeout(function () { scanningLock = false; }, 3000);
        });
    }

    function qrboxSize(viewfinderWidth, viewfinderHeight) {
        var side = Math.min(viewfinderWidth, viewfinderHeight) * 0.85;
        var edge = Math.max(200, Math.min(side, 320));
        return { width: edge, height: edge };
    }

    function stopCamera() {
        if (!scanner || !cameraOn) return;
        var p = scanner.stop().then(function () {
            if (scanner.clear) return scanner.clear();
        }).catch(function () {});
        cameraOn = false;
        if (startBtn) startBtn.hidden = false;
        if (stopBtn) stopBtn.hidden = true;
        setStatus('Камера остановлена');
        return p;
    }

    function startCamera() {
        if (typeof Html5Qrcode === 'undefined') {
            setStatus('Библиотека сканера не загрузилась');
            showResult({ error: 'Обновите страницу' }, true);
            return;
        }
        if (!scanner) {
            scanner = new Html5Qrcode('qr-reader', { verbose: false });
        }
        if (cameraOn) return;

        setStatus('Запрос доступа к камере…');
        if (startBtn) startBtn.disabled = true;

        var config = {
            fps: 12,
            qrbox: qrboxSize,
            aspectRatio: 1.0,
            disableFlip: false,
        };

        function onCameraReady(label) {
            cameraOn = true;
            if (startBtn) {
                startBtn.hidden = true;
                startBtn.disabled = false;
            }
            if (stopBtn) stopBtn.hidden = false;
            setStatus(label || 'Наведите камеру на QR-код');
            if (resultEl) resultEl.hidden = true;
            if (scanAgainBtn) scanAgainBtn.hidden = true;
        }

        scanner.start(
            { facingMode: 'environment' },
            config,
            onScanSuccess,
            function () { /* кадры без QR — норма */ }
        ).then(function () {
            onCameraReady('Наведите камеру на QR-код');
        }).catch(function () {
            return scanner.start(
                { facingMode: 'user' },
                config,
                onScanSuccess,
                function () {}
            ).then(function () {
                onCameraReady('Фронтальная камера — держите телефон удобнее');
            });
        }).catch(function (err) {
            if (startBtn) {
                startBtn.hidden = false;
                startBtn.disabled = false;
            }
            var msg = (err && err.message) ? err.message : String(err);
            setStatus('Камера недоступна');
            showResult({
                error: 'Разрешите камеру в браузере. На телефоне сайт должен открываться по HTTPS (не http).',
            }, true);
        });
    }

    if (startBtn) startBtn.addEventListener('click', startCamera);
    if (stopBtn) stopBtn.addEventListener('click', stopCamera);

    if (scanAgainBtn) {
        scanAgainBtn.addEventListener('click', function () {
            if (resultEl) resultEl.hidden = true;
            scanAgainBtn.hidden = true;
            scanningLock = false;
            if (!cameraOn) startCamera();
            else setStatus('Наведите камеру на QR-код');
        });
    }

    var manualBtn = document.getElementById('manualVerifyBtn');
    var manualInput = document.getElementById('manualToken');
    if (manualBtn) {
        manualBtn.addEventListener('click', function () {
            verify(manualInput ? manualInput.value : '');
        });
    }

    window.addEventListener('pagehide', function () {
        stopCamera();
    });
})();
