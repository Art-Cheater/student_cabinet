(function () {
    var modal = document.getElementById('event-modal');
    if (!modal) return;

    var currentEv = null;
    var userRole = document.body.dataset.userRole || '';

    function qs(id) { return document.getElementById(id); }

    function fillFileList(ul, files, emptyEl) {
        if (!ul) return;
        ul.innerHTML = '';
        var list = files || [];
        if (emptyEl) emptyEl.style.display = list.length ? 'none' : '';
        list.forEach(function (a) {
            var li = document.createElement('li');
            var link = document.createElement('a');
            link.href = a.url;
            link.target = '_blank';
            link.rel = 'noopener';
            link.textContent = a.name;
            li.appendChild(link);
            ul.appendChild(li);
        });
    }

    function openModal(ev) {
        currentEv = ev;
        qs('event-modal-title').textContent = ev.title || 'Событие';
        qs('event-modal-time').textContent =
            (ev.start || '').replace('T', ' ').slice(0, 16) +
            (ev.end ? ' – ' + (ev.end || '').slice(11, 16) : '');
        var extra = [];
        if (ev.teacher) extra.push(ev.teacher);
        if (ev.classroom) extra.push(ev.classroom);
        qs('event-modal-extra').textContent = extra.join(' · ');

        var slotEdit = qs('event-modal-slot-edit');
        slotEdit.style.display =
            userRole === 'teacher' && ev.type === 'office_slot' && ev.slot_id ? '' : 'none';

        if (ev.type === 'office_slot' && ev.slot_id) {
            var sd = (ev.start || '').slice(0, 10);
            qs('ev-slot-date').value = sd;
            qs('ev-slot-start').value = (ev.start || '').slice(11, 16);
            qs('ev-slot-end').value = (ev.end || '').slice(11, 16);
            qs('ev-slot-room').value = ev.classroom || '';
            qs('ev-slot-topic').value = ev.title || '';
            qs('ev-slot-max').value = ev.max_students || 1;
        }

        var teacherUpload = qs('event-modal-teacher-upload-wrap');
        if (teacherUpload) {
            teacherUpload.style.display =
                userRole === 'teacher' && (ev.type === 'office_slot' || ev.slot_id) ? '' : 'none';
        }

        var bookingActions = qs('event-modal-booking-actions');
        if (bookingActions) {
            var canCancel = userRole === 'student' && ev.type === 'booking' && ev.booking_id
                && ev.status !== 'cancelled' && ev.status !== 'rejected';
            bookingActions.style.display = canCancel ? '' : 'none';
        }

        modal.classList.add('open');
        loadMeta(ev);
    }

    function closeModal() {
        modal.classList.remove('open');
        currentEv = null;
    }

    async function loadMeta(ev) {
        var key = ev.event_key || ev.id;
        if (!key) return;
        try {
            var r = await fetch('/api/calendar/event-meta?event_key=' + encodeURIComponent(key));
            var data = await r.json();
            qs('event-modal-note').value = data.note || '';
            var teacherFiles = data.teacher_files || data.attachments || [];
            fillFileList(
                qs('event-modal-teacher-files'),
                teacherFiles,
                qs('event-modal-teacher-files-empty'),
            );
            fillFileList(qs('event-modal-my-files'), data.my_files || [], null);
        } catch (e) { /* ignore */ }
    }

    async function saveNote() {
        if (!currentEv) return;
        var key = currentEv.event_key || currentEv.id;
        var r = await fetch('/api/calendar/notes', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event_key: key,
                event_type: currentEv.type || 'lesson',
                note_text: qs('event-modal-note').value,
            }),
        });
        var data = await r.json();
        if (data.ok && window.showToast) {
            window.showToast(data.message || 'Заметка сохранена');
        }
    }

    async function saveSlot(confirmOverlap) {
        if (!currentEv || !currentEv.slot_id) return;
        sessionStorage.setItem('scrollRestoreY', String(window.scrollY));
        var body = {
            slot_date: qs('ev-slot-date').value,
            time_start: qs('ev-slot-start').value,
            time_end: qs('ev-slot-end').value,
            room_display: qs('ev-slot-room').value,
            topic: qs('ev-slot-topic').value,
            max_students: parseInt(qs('ev-slot-max').value, 10) || 1,
            confirm_overlap: !!confirmOverlap,
        };
        var r = await fetch('/api/teacher/slots/' + currentEv.slot_id, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = await r.json();
        if (data.ok) location.reload();
        else if (data.need_confirm && confirm('В это время пара. Сохранить всё равно?')) {
            await saveSlot(true);
        } else alert(data.error || 'Ошибка');
    }

    async function deleteSlot() {
        if (!currentEv || !currentEv.slot_id) return;
        if (!confirm('Удалить этот слот?')) return;
        sessionStorage.setItem('scrollRestoreY', String(window.scrollY));
        var r = await fetch('/api/teacher/slots/' + currentEv.slot_id, { method: 'DELETE' });
        var data = await r.json();
        if (data.ok) location.reload();
        else alert(data.error || 'Ошибка');
    }

    async function cancelBooking() {
        if (!currentEv || !currentEv.booking_id) return;
        if (!confirm('Отменить запись?')) return;
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/appointment/cancel/' + currentEv.booking_id;
        document.body.appendChild(form);
        form.submit();
    }

    async function uploadTeacherFile() {
        if (!currentEv) return;
        var fileInput = qs('event-modal-file');
        if (!fileInput.files.length) return;
        var fd = new FormData();
        fd.append('event_key', currentEv.event_key || currentEv.id);
        fd.append('event_type', currentEv.type || 'lesson');
        if (currentEv.slot_id) fd.append('slot_id', String(currentEv.slot_id));
        fd.append('file', fileInput.files[0]);
        var r = await fetch('/api/calendar/attachments', { method: 'POST', body: fd });
        var data = await r.json();
        if (data.ok) {
            if (window.showToast) window.showToast('Файл добавлен');
            loadMeta(currentEv);
            fileInput.value = '';
        } else if (window.showToast) {
            window.showToast(data.error || 'Ошибка загрузки', 'error');
        }
    }

    async function uploadMyFile() {
        if (!currentEv) return;
        var fileInput = qs('event-modal-my-file');
        if (!fileInput.files.length) return;
        var fd = new FormData();
        fd.append('event_key', currentEv.event_key || currentEv.id);
        fd.append('event_type', currentEv.type || 'lesson');
        fd.append('file', fileInput.files[0]);
        var r = await fetch('/api/calendar/note-files', { method: 'POST', body: fd });
        var data = await r.json();
        if (data.ok) {
            if (window.showToast) window.showToast('Файл добавлен');
            loadMeta(currentEv);
            fileInput.value = '';
        } else if (window.showToast) {
            window.showToast(data.error || 'Ошибка загрузки', 'error');
        }
    }

    qs('event-modal-close').onclick = closeModal;
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });
    qs('event-modal-save-note').onclick = saveNote;
    qs('ev-slot-save').onclick = function () { saveSlot(false); };
    qs('ev-slot-delete').onclick = deleteSlot;
    var cancelBookingBtn = qs('event-modal-cancel-booking');
    if (cancelBookingBtn) cancelBookingBtn.onclick = cancelBooking;
    var uploadBtn = qs('event-modal-upload-btn');
    if (uploadBtn) uploadBtn.onclick = uploadTeacherFile;
    var myUploadBtn = qs('event-modal-my-upload-btn');
    if (myUploadBtn) myUploadBtn.onclick = uploadMyFile;

    window.EventModal = { open: openModal, close: closeModal };

    var sy = sessionStorage.getItem('scrollRestoreY');
    if (sy) {
        sessionStorage.removeItem('scrollRestoreY');
        window.scrollTo(0, parseInt(sy, 10) || 0);
    }
})();
