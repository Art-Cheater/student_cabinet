(function () {
    var statusEl = document.getElementById('cameraStatus');
    var startBtn = document.getElementById('startCameraBtn');
    var stopBtn = document.getElementById('stopCameraBtn');
    var resultEl = document.getElementById('guardPassResult');
    var loadingEl = document.getElementById('guardLoading');
    var scanner = null;
    var scanningLock = false;
    var cameraOn = false;
    var lastResultData = null;

    function setStatus(text) {
        if (statusEl) statusEl.textContent = text;
    }

    function setLoading(on) {
        if (loadingEl) loadingEl.classList.toggle('is-active', !!on);
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function formatValidUntil(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            if (isNaN(d.getTime())) return iso;
            return d.toLocaleString('ru-RU', {
                day: '2-digit', month: '2-digit', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
            });
        } catch (e) {
            return iso;
        }
    }

    function getHtml5QrcodeClass() {
        if (typeof Html5Qrcode !== 'undefined') return Html5Qrcode;
        if (window.__Html5QrcodeLibrary__ && window.__Html5QrcodeLibrary__.Html5Qrcode) {
            return window.__Html5QrcodeLibrary__.Html5Qrcode;
        }
        return null;
    }

    function parseToken(text) {
        var t = (text || '').trim();
        if (!t) return '';
        try {
            var u = new URL(t);
            var parts = u.pathname.split('/').filter(Boolean);
            var gi = parts.indexOf('gate');
            if (gi >= 0 && parts[gi + 1]) return parts[gi + 1];
        } catch (e) { /* plain uuid */ }
        if (t.indexOf('/gate/') !== -1) {
            var seg = t.split('/gate/')[1];
            return (seg || '').split(/[?#]/)[0];
        }
        return t;
    }

    function row(label, value) {
        if (value == null || value === '') return '';
        return '<div class="access-data-row"><span>' + escapeHtml(label) + '</span><span>' +
            escapeHtml(value) + '</span></div>';
    }

    function hidePassResult() {
        lastResultData = null;
        if (resultEl) {
            resultEl.hidden = true;
            resultEl.innerHTML = '';
        }
    }

    function showPassResult(data, isError) {
        if (!resultEl) return;
        resultEl.hidden = false;

        if (isError) {
            resultEl.className = 'guard-result-card is-error';
            resultEl.innerHTML =
                '<p class="guard-pass-error">' + escapeHtml(data.error || 'Ошибка проверки') + '</p>';
            if (navigator.vibrate) navigator.vibrate(200);
            return;
        }

        lastResultData = data;
        var isStudent = data.subject_type === 'student';
        var title = isStudent ? 'Студенческий билет' : 'Пропуск преподавателя';
        var html = '<div class="guard-result-card is-ok">';
        html += '<div class="guard-status-ok">';
        html += '<div class="guard-status-icon">';
        html += '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">';
        html += '<path d="M20 6L9 17l-5-5"/></svg></div>';
        html += '<span class="guard-status-text">QR-код действителен / подтверждён</span></div>';
        html += '<p class="access-section-title">Данные посетителя</p>';
        html += '<div class="guard-pass-photo-wrap" style="text-align:center;margin-bottom:16px;">';
        if (data.photo_url) {
            html += '<img src="' + escapeHtml(data.photo_url) + '" alt="Фото" class="guard-pass-photo" ' +
                'style="width:140px;height:140px;object-fit:cover;border-radius:12px;" ' +
                'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">';
        }
        html += '<div class="guard-pass-photo-placeholder" style="' +
            (data.photo_url ? 'display:none;' : '') +
            'width:140px;height:140px;margin:0 auto;border-radius:50%;' +
            'background:linear-gradient(135deg,var(--access-accent),var(--access-accent-dark));' +
            'color:#fff;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:700;">' +
            escapeHtml(data.photo_initials || '?') + '</div></div>';
        html += '<p class="access-fio" style="text-align:center;margin-bottom:12px;">' + escapeHtml(data.fio || '') + '</p>';
        html += '<p style="text-align:center;font-weight:600;margin-bottom:8px;">' + escapeHtml(title) + '</p>';
        if (isStudent) {
            html += row('Группа', data.group);
            html += row('Номер пропуска', data.pass_number || data.card_number_masked);
        } else {
            html += row('№ пропуска', data.pass_number);
            html += row('Должность', data.position_title);
        }
        html += row('Действует до', formatValidUntil(data.valid_until));
        html += '<p class="guard-privacy-badge">ФИО не содержится в QR-коде</p>';
        html += '<button type="button" class="guard-confirm-btn" id="guardConfirmBtn">Подтвердить пропуск</button>';
        html += '</div>';

        resultEl.className = '';
        resultEl.innerHTML = html;
        var confirmBtn = document.getElementById('guardConfirmBtn');
        if (confirmBtn) {
            confirmBtn.onclick = function () {
                hidePassResult();
                setStatus('Готов к следующему сканированию');
                scanningLock = false;
            };
        }
        if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
        resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async function verify(raw) {
        var token = parseToken(raw);
        if (!token) {
            showPassResult({ error: 'Не удалось прочитать код' }, true);
            return;
        }
        setStatus('Проверка…');
        setLoading(true);
        try {
            var r = await fetch('/api/guard/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ token: token }),
            });
            var data = await r.json();
            if (data.ok) {
                showPassResult(data, false);
                setStatus('Пропуск подтверждён — нажмите «Подтвердить пропуск»');
            } else {
                showPassResult(data, true);
                setStatus('Пропуск не принят');
                setTimeout(function () { scanningLock = false; }, 2000);
            }
        } catch (e) {
            showPassResult({ error: 'Нет связи с сервером' }, true);
            setStatus('Ошибка сети');
            setTimeout(function () { scanningLock = false; }, 2000);
        } finally {
            setLoading(false);
        }
    }

    function onScanSuccess(decodedText) {
        if (scanningLock || !decodedText) return;
        scanningLock = true;
        verify(decodedText);
    }

    function qrboxSize(viewfinderWidth, viewfinderHeight) {
        var side = Math.min(viewfinderWidth, viewfinderHeight) * 0.85;
        var edge = Math.max(200, Math.min(side, 320));
        return { width: edge, height: edge };
    }

    function stopCamera() {
        if (!scanner || !cameraOn) return;
        scanner.stop().then(function () {
            if (scanner.clear) return scanner.clear();
        }).catch(function () {});
        cameraOn = false;
        if (startBtn) startBtn.hidden = false;
        if (stopBtn) stopBtn.hidden = true;
    }

    function startCamera() {
        var Html5Qrcode = getHtml5QrcodeClass();
        if (!Html5Qrcode) {
            setStatus('Сканер не загрузился');
            showPassResult({
                error: 'Не загрузилась библиотека камеры. Обновите страницу или введите ссылку вручную.',
            }, true);
            return;
        }
        if (!scanner) {
            scanner = new Html5Qrcode('qr-reader', { verbose: false });
        }
        if (cameraOn) return;

        setStatus('Запрос доступа к камере…');
        if (startBtn) startBtn.disabled = true;
        hidePassResult();

        var config = { fps: 12, qrbox: qrboxSize, aspectRatio: 1.0 };

        function onCameraReady(label) {
            cameraOn = true;
            if (startBtn) {
                startBtn.hidden = true;
                startBtn.disabled = false;
            }
            if (stopBtn) stopBtn.hidden = false;
            setStatus(label || 'Наведите камеру на QR-код');
        }

        scanner.start(
            { facingMode: 'environment' },
            config,
            onScanSuccess,
            function () {}
        ).then(function () {
            onCameraReady('Наведите камеру на QR-код');
        }).catch(function () {
            return scanner.start(
                { facingMode: 'user' },
                config,
                onScanSuccess,
                function () {}
            ).then(function () {
                onCameraReady('Фронтальная камера');
            });
        }).catch(function () {
            if (startBtn) {
                startBtn.hidden = false;
                startBtn.disabled = false;
            }
            setStatus('Камера недоступна');
            showPassResult({
                error: 'Разрешите камеру в браузере. На iPhone нужен HTTPS.',
            }, true);
        });
    }

    if (startBtn) startBtn.addEventListener('click', startCamera);
    if (stopBtn) stopBtn.addEventListener('click', function () {
        stopCamera();
        setStatus('Камера остановлена');
    });

    var manualBtn = document.getElementById('manualVerifyBtn');
    var manualInput = document.getElementById('manualToken');
    if (manualBtn) {
        manualBtn.addEventListener('click', function () {
            scanningLock = true;
            verify(manualInput ? manualInput.value : '');
        });
    }

    window.addEventListener('pagehide', stopCamera);
})();
