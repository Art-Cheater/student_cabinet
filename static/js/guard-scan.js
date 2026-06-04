(function () {
    var statusEl = document.getElementById('cameraStatus');
    var startBtn = document.getElementById('startCameraBtn');
    var stopBtn = document.getElementById('stopCameraBtn');
    var modal = document.getElementById('guard-pass-modal');
    var modalBody = document.getElementById('guard-pass-modal-body');
    var modalClose = document.getElementById('guard-pass-modal-close');
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

    function openModal() {
        if (!modal) return;
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        if (!modal) return;
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    function row(label, value) {
        if (value == null || value === '') return '';
        return '<p><strong>' + escapeHtml(label) + ':</strong> ' + escapeHtml(value) + '</p>';
    }

    function showPassModal(data, isError) {
        if (!modalBody) return;
        openModal();
        if (isError) {
            modalBody.innerHTML =
                '<h3 class="guard-modal-title guard-modal-title--error">Отказ</h3>' +
                '<p class="guard-modal-error">' + escapeHtml(data.error || 'Ошибка проверки') + '</p>' +
                '<button type="button" class="btn btn-primary btn-block" id="guard-modal-ok">Закрыть</button>';
            if (navigator.vibrate) navigator.vibrate(200);
            bindModalOk();
            return;
        }

        var isStudent = data.subject_type === 'student';
        var title = isStudent ? 'Студенческий билет' : 'Пропуск преподавателя';
        var html = '<h3 class="guard-modal-title guard-modal-title--ok">' + escapeHtml(title) + '</h3>';
        html += '<p class="guard-modal-badge">Допуск разрешён</p>';

        if (data.photo_url) {
            html += '<div class="guard-modal-photo-wrap">' +
                '<img src="' + escapeHtml(data.photo_url) + '" alt="Фото" class="guard-modal-photo">' +
                '</div>';
        }

        html += '<div class="guard-modal-card student-cabinet-card">';
        html += '<p class="guard-modal-fio">' + escapeHtml(data.fio || '') + '</p>';
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
        html += '<p class="hint guard-modal-valid">Действует до: ' + escapeHtml(formatValidUntil(data.valid_until)) + '</p>';
        html += '</div>';
        html += '<button type="button" class="btn btn-accent btn-block" id="guard-modal-ok">Следующий</button>';
        modalBody.innerHTML = html;
        if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
        bindModalOk();
    }

    function bindModalOk() {
        var ok = document.getElementById('guard-modal-ok');
        if (ok) {
            ok.onclick = function () {
                closeModal();
                scanningLock = false;
                setStatus(cameraOn ? 'Наведите камеру на QR-код' : 'Нажмите «Включить камеру»');
            };
        }
    }

    async function verify(raw) {
        var token = parseToken(raw);
        if (!token) {
            showPassModal({ error: 'Не удалось прочитать код' }, true);
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
                stopCamera();
                showPassModal(data, false);
                setStatus('Пропуск подтверждён');
            } else {
                showPassModal(data, true);
                setStatus('Пропуск не принят');
            }
        } catch (e) {
            showPassModal({ error: 'Нет связи с сервером' }, true);
            setStatus('Ошибка сети');
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
            showPassModal({
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

        var config = { fps: 12, qrbox: qrboxSize, aspectRatio: 1.0 };

        function onCameraReady(label) {
            cameraOn = true;
            if (startBtn) {
                startBtn.hidden = true;
                startBtn.disabled = false;
            }
            if (stopBtn) stopBtn.hidden = false;
            setStatus(label || 'Наведите камеру на QR-код');
            closeModal();
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
            showPassModal({
                error: 'Разрешите камеру в браузере. На iPhone надёжнее открыть сайт по HTTPS.',
            }, true);
        });
    }

    if (startBtn) startBtn.addEventListener('click', startCamera);
    if (stopBtn) stopBtn.addEventListener('click', function () {
        stopCamera();
        setStatus('Камера остановлена');
    });

    if (modalClose) modalClose.addEventListener('click', closeModal);
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });
    }

    var manualBtn = document.getElementById('manualVerifyBtn');
    var manualInput = document.getElementById('manualToken');
    if (manualBtn) {
        manualBtn.addEventListener('click', function () {
            verify(manualInput ? manualInput.value : '');
        });
    }

    window.addEventListener('pagehide', stopCamera);
})();
