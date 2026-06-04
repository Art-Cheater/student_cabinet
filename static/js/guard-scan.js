(function () {
    var statusEl = document.getElementById('cameraStatus');
    var startBtn = document.getElementById('startCameraBtn');
    var stopBtn = document.getElementById('stopCameraBtn');
    var resultEl = document.getElementById('guardPassResult');
    var scanner = null;
    var scanningLock = false;
    var cameraOn = false;

    function setStatus(text) {
        if (statusEl) statusEl.textContent = text;
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
        return '<p><strong>' + escapeHtml(label) + ':</strong> ' + escapeHtml(value) + '</p>';
    }

    function showPassResult(data, isError) {
        if (!resultEl) return;
        resultEl.hidden = false;

        if (isError) {
            resultEl.className = 'guard-pass-panel guard-pass-panel--error';
            resultEl.innerHTML =
                '<h3 class="guard-pass-title">Отказ</h3>' +
                '<p class="guard-pass-error">' + escapeHtml(data.error || 'Ошибка проверки') + '</p>';
            if (navigator.vibrate) navigator.vibrate(200);
        } else {
            var isStudent = data.subject_type === 'student';
            var title = isStudent ? 'Студенческий билет' : 'Пропуск преподавателя';
            var html = '<h3 class="guard-pass-title guard-pass-title--ok">' + escapeHtml(title) + '</h3>';
            html += '<p class="guard-pass-badge">Допуск разрешён</p>';

            if (data.photo_url) {
                html += '<div class="guard-pass-photo-wrap">' +
                    '<img src="' + escapeHtml(data.photo_url) + '" alt="Фото" class="guard-pass-photo" ' +
                    'loading="eager" decoding="async" ' +
                    'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\';">' +
                    '<p class="hint guard-pass-photo-missing" style="display:none;">Фото не загружено</p>' +
                    '</div>';
            }

            html += '<div class="guard-pass-card student-cabinet-card">';
            html += '<p class="guard-pass-fio">' + escapeHtml(data.fio || '') + '</p>';
            if (isStudent) {
                html += row('Группа', data.group);
                html += row('ID студента', data.student_id);
                html += row('Курс', data.course_number);
                html += row('Форма обучения', data.study_form);
                html += row('Дата выдачи', data.issue_date);
                html += row('Номер студбилета', data.card_number_masked);
            } else {
                html += row('Должность', data.position_title);
                html += row('Подразделение', data.department);
                html += row('№ удостоверения', data.pass_number);
            }
            html += '<p class="hint guard-pass-valid">Действует до: ' + escapeHtml(formatValidUntil(data.valid_until)) + '</p>';
            html += '</div>';

            resultEl.className = 'guard-pass-panel guard-pass-panel--ok';
            resultEl.innerHTML = html;
            if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
        }

        resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hidePassResult() {
        if (resultEl) {
            resultEl.hidden = true;
            resultEl.innerHTML = '';
        }
    }

    async function verify(raw) {
        var token = parseToken(raw);
        if (!token) {
            showPassResult({ error: 'Не удалось прочитать код' }, true);
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
                showPassResult(data, false);
                setStatus('Пропуск подтверждён — можно сканировать следующий');
                scanningLock = false;
            } else {
                showPassResult(data, true);
                setStatus('Пропуск не принят');
                setTimeout(function () { scanningLock = false; }, 2000);
            }
        } catch (e) {
            showPassResult({ error: 'Нет связи с сервером' }, true);
            setStatus('Ошибка сети');
            setTimeout(function () { scanningLock = false; }, 2000);
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
            verify(manualInput ? manualInput.value : '');
        });
    }

    window.addEventListener('pagehide', stopCamera);
})();
