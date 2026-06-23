(function () {
    var modal = document.getElementById('event-modal');
    if (!modal) return;

    var currentEv = null;
    var editMode = false;
    var userRole = document.body.dataset.userRole || '';

    function qs(id) { return document.getElementById(id); }

    function fillFileList(ul, files, emptyEl, opts) {
        opts = opts || {};
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
            link.textContent = a.name || a.fio || 'Файл';
            li.appendChild(link);
            if (a.fio) {
                li.appendChild(document.createTextNode(' (' + a.fio + ')'));
            } else if (a.group) {
                li.appendChild(document.createTextNode(' (' + a.group + ')'));
            }
            if (opts.deletable && a.id) {
                var del = document.createElement('button');
                del.type = 'button';
                del.className = 'btn btn-ghost btn-sm';
                del.textContent = 'Удалить';
                del.style.marginLeft = '0.5rem';
                del.onclick = async function () {
                    if (!confirm('Удалить файл?')) return;
                    var r = await fetch('/api/calendar/note-files/' + a.id, { method: 'DELETE' });
                    var data = await r.json();
                    if (!r.ok) {
                        alert(data.error || 'Ошибка');
                        return;
                    }
                    if (window.showToast) window.showToast(data.message || 'Удалено');
                    loadMeta(currentEv);
                };
                li.appendChild(del);
            }
            ul.appendChild(li);
        });
    }

    function syncNoteToCalendar(key, text) {
        window.calendarNotesMap = window.calendarNotesMap || {};
        text = (text || '').trim();
        if (text) {
            window.calendarNotesMap[key] = text;
        } else {
            delete window.calendarNotesMap[key];
        }
        document.querySelectorAll('.calendar-event[data-event-key]').forEach(function (div) {
            if (div.dataset.eventKey !== key) return;
            var old = div.querySelector('.calendar-event-note');
            if (old) old.remove();
            if (!text) return;
            var noteEl = document.createElement('div');
            noteEl.className = 'calendar-event-note';
            if (text.length <= 48) {
                noteEl.textContent = text;
            } else {
                noteEl.className += ' calendar-event-note--hint';
                noteEl.title = text;
                noteEl.textContent = '📝 заметка';
            }
            div.appendChild(noteEl);
        });
    }

    function fillSubmissionList(ul, files) {
        if (!ul) return;
        ul.innerHTML = '';
        (files || []).forEach(function (a) {
            var li = document.createElement('li');
            var link = document.createElement('a');
            link.href = a.url;
            link.target = '_blank';
            link.rel = 'noopener';
            link.textContent = a.name || 'Файл';
            li.appendChild(link);
            if (a.id) {
                var del = document.createElement('button');
                del.type = 'button';
                del.className = 'btn btn-ghost btn-sm';
                del.textContent = 'Удалить';
                del.style.marginLeft = '0.5rem';
                del.onclick = async function () {
                    if (!confirm('Удалить файл?')) return;
                    await fetch('/api/slots/submissions/' + a.id, { method: 'DELETE' });
                    loadMeta(currentEv);
                };
                li.appendChild(del);
            }
            ul.appendChild(li);
        });
    }

    function fillQueueList(ul, items, isTeacher) {
        if (!ul) return;
        ul.innerHTML = '';
        (items || []).forEach(function (q) {
            var li = document.createElement('li');
            if (isTeacher && q.id) {
                var label = document.createElement('label');
                label.className = 'queue-passed-label';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !!q.passed;
                cb.title = 'Прошёл у преподавателя';
                cb.onchange = function () { toggleQueuePassed(q.id, cb.checked); };
                label.appendChild(cb);
                label.appendChild(document.createTextNode(
                    ' ' + q.position + '. ' + q.fio + (q.group ? ' (' + q.group + ')' : ''),
                ));
                if (q.passed) label.classList.add('queue-passed-done');
                li.appendChild(label);
            } else {
                li.textContent = q.position + '. ' + q.fio + (q.group ? ' (' + q.group + ')' : '');
            }
            ul.appendChild(li);
        });
    }

    async function toggleQueuePassed(entryId, passed) {
        if (!currentEv || !currentEv.slot_id) return;
        var r = await fetch(
            '/api/slots/' + currentEv.slot_id + '/queue/' + entryId,
            {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ passed: passed }),
            },
        );
        var data = await r.json();
        if (!r.ok && window.showToast) {
            window.showToast(data.error || 'Ошибка', 'error');
        }
        loadMeta(currentEv);
    }

    function setEditMode(on) {
        editMode = !!on;
        var slotEdit = qs('event-modal-slot-edit');
        var lessonEdit = qs('event-modal-lesson-edit');
        var slotMaterials = qs('event-modal-slot-materials-edit');
        var viewPanel = qs('event-modal-view-panel');
        var editBtn = qs('event-modal-edit-btn');
        var isSlot = currentEv && currentEv.type === 'office_slot' && currentEv.slot_id;
        var isLesson = currentEv && currentEv.type === 'lesson' && currentEv.is_own_lesson;
        if (slotEdit) slotEdit.style.display = editMode && isSlot ? '' : 'none';
        if (lessonEdit) lessonEdit.style.display = editMode && isLesson ? '' : 'none';
        if (slotMaterials) slotMaterials.style.display = editMode && isSlot ? '' : 'none';
        if (viewPanel) viewPanel.style.display = editMode ? 'none' : '';
        if (editBtn) editBtn.classList.toggle('active', editMode);
    }

    function canTeacherEdit(ev) {
        if (userRole !== 'teacher' || !ev) return false;
        if (ev.type === 'office_slot' && ev.slot_id) return true;
        if (ev.type === 'lesson' && ev.is_own_lesson === true) return true;
        return false;
    }

    function openModal(ev, opts) {
        opts = opts || {};
        currentEv = ev;
        editMode = false;
        qs('event-modal-title').textContent = ev.title || 'Событие';
        qs('event-modal-time').textContent =
            (ev.start || '').replace('T', ' ').slice(0, 16) +
            (ev.end ? ' – ' + (ev.end || '').slice(11, 16) : '');
        var extra = [];
        if (ev.teacher) extra.push(ev.teacher);
        if (ev.classroom) extra.push(ev.classroom);
        qs('event-modal-extra').textContent = extra.join(' · ');

        var isTeacherSlot = userRole === 'teacher' && ev.type === 'office_slot' && ev.slot_id;
        var editBtn = qs('event-modal-edit-btn');
        if (editBtn) editBtn.hidden = !canTeacherEdit(ev);

        if (ev.type === 'office_slot' && ev.slot_id) {
            var sd = (ev.start || '').slice(0, 10);
            qs('ev-slot-date').value = sd;
            qs('ev-slot-start').value = (ev.start || '').slice(11, 16);
            qs('ev-slot-end').value = (ev.end || '').slice(11, 16);
            qs('ev-slot-room').value = ev.classroom || '';
            qs('ev-slot-topic').value = ev.title || '';
            qs('ev-slot-max').value = ev.max_students || 1;
            if (qs('ev-slot-enable-queue')) {
                qs('ev-slot-enable-queue').checked = !!ev.enable_queue;
            }
            if (qs('ev-slot-enable-submission')) {
                qs('ev-slot-enable-submission').checked = !!ev.enable_submission;
            }
        }

        var teacherUpload = qs('event-modal-slot-materials-edit');
        if (teacherUpload) teacherUpload.style.display = 'none';

        var bookingActions = qs('event-modal-booking-actions');
        if (bookingActions) {
            var canCancel = userRole === 'student' && ev.type === 'booking' && ev.booking_id
                && ev.status !== 'cancelled' && ev.status !== 'rejected';
            bookingActions.style.display = canCancel ? '' : 'none';
        }

        setEditMode(!!opts.edit && canTeacherEdit(ev));
        modal.classList.add('open');

        var noteBlock = qs('event-modal-note-block') || document.querySelector('.event-modal-note-block');
        if (noteBlock) {
            var showNote = userRole === 'student' &&
                (ev.type === 'lesson' || ev.type === 'booking');
            noteBlock.style.display = showNote || userRole !== 'student' ? '' : 'none';
            var noteHint = qs('event-modal-note-hint');
            if (noteHint) {
                noteHint.style.display = userRole === 'student' ? '' : 'none';
            }
        }

        loadMeta(ev);
    }

    function closeModal() {
        modal.classList.remove('open');
        currentEv = null;
        editMode = false;
    }

    async function loadMeta(ev) {
        var key = ev.event_key || ev.id;
        if (!key) return;
        try {
            var r = await fetch('/api/calendar/event-meta?event_key=' + encodeURIComponent(key));
            var data = await r.json();
            qs('event-modal-note').value = data.note || '';
            fillFileList(
                qs('event-modal-teacher-files'),
                data.teacher_files || data.attachments || [],
                qs('event-modal-teacher-files-empty'),
            );
            fillFileList(qs('event-modal-my-files'), data.my_files || [], null, { deletable: true });

            var slotInfo = qs('event-modal-slot-info');
            if (slotInfo && userRole === 'teacher' && ev.type === 'office_slot') {
                var html = '';
                if (data.bookings && data.bookings.length) {
                    html += '<h4>Записавшиеся</h4><ul>';
                    data.bookings.forEach(function (b) {
                        html += '<li>' + b.fio + ' (' + b.status + ')' +
                            (b.group ? ' — ' + b.group : '') + '</li>';
                    });
                    html += '</ul>';
                }
                slotInfo.innerHTML = html || '<p class="hint">Пока нет записей</p>';
                slotInfo.hidden = false;
            } else if (slotInfo) {
                slotInfo.hidden = true;
            }

            var queueWrap = qs('event-modal-queue-wrap');
            if (queueWrap) {
                var showQ = (data.slot_flags && data.slot_flags.enable_queue) &&
                    ((data.queue && data.queue.length) || userRole === 'teacher');
                queueWrap.hidden = !showQ;
                if (showQ) {
                    fillQueueList(
                        qs('event-modal-queue-list'),
                        data.queue,
                        userRole === 'teacher',
                    );
                }
            }

            var subWrap = qs('event-modal-submissions-wrap');
            if (subWrap) {
                var showS = data.slot_flags && data.slot_flags.enable_submission &&
                    data.submissions && data.submissions.length;
                subWrap.hidden = !showS;
                if (showS) {
                    fillFileList(qs('event-modal-submissions-list'), data.submissions, null);
                }
            }

            var studentSub = qs('event-modal-student-submission-wrap');
            if (studentSub) {
                studentSub.style.display =
                    userRole === 'student' && data.slot_flags && data.slot_flags.enable_submission
                        ? '' : 'none';
                if (studentSub.style.display !== 'none') {
                    fillSubmissionList(qs('event-modal-my-submission'), data.submissions || []);
                }
            }

            var queueActions = qs('event-modal-queue-actions');
            if (queueActions) {
                var showQA = userRole === 'student' && data.slot_flags && data.slot_flags.enable_queue;
                queueActions.style.display = showQA ? '' : 'none';
                if (showQA) {
                    var canJoin = !!data.can_join_queue;
                    qs('event-modal-join-queue').hidden = !!data.in_queue || !canJoin;
                    qs('event-modal-leave-queue').hidden = !data.in_queue;
                    var hintOff = document.getElementById('queue-hint-off');
                    if (hintOff) hintOff.remove();
                    if (!data.in_queue && !canJoin && data.slot_flags.enable_queue) {
                        var p = document.createElement('p');
                        p.className = 'hint';
                        p.id = 'queue-hint-off';
                        p.textContent = 'Очередь недоступна для вашей группы.';
                        queueActions.appendChild(p);
                    }
                }
            }

            if (ev.type === 'office_slot' && ev.slot_id && data.slot_flags) {
                if (qs('ev-slot-enable-queue')) {
                    qs('ev-slot-enable-queue').checked = !!data.slot_flags.enable_queue;
                }
                if (qs('ev-slot-enable-submission')) {
                    qs('ev-slot-enable-submission').checked = !!data.slot_flags.enable_submission;
                }
                ev.enable_queue = data.slot_flags.enable_queue;
                ev.enable_submission = data.slot_flags.enable_submission;
            }
        } catch (e) { /* ignore */ }
    }

    async function saveNoteAndFiles() {
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
        if (!r.ok) {
            alert(data.error || 'Не удалось сохранить заметку');
            return;
        }
        var fileInput = qs('event-modal-my-file');
        if (fileInput && fileInput.files.length) {
            var fd = new FormData();
            fd.append('event_key', key);
            fd.append('event_type', currentEv.type || 'lesson');
            fd.append('file', fileInput.files[0]);
            var fr = await fetch('/api/calendar/note-files', { method: 'POST', body: fd });
            var fdata = await fr.json();
            if (!fr.ok) {
                alert(fdata.error || 'Не удалось загрузить файл');
                return;
            }
            fileInput.value = '';
        }
        if (window.showToast) {
            window.showToast(data.message || 'Сохранено');
        }
        syncNoteToCalendar(key, qs('event-modal-note').value);
        loadMeta(currentEv);
    }

    async function deleteNote() {
        if (!currentEv) return;
        if (!confirm('Удалить заметку?')) return;
        var key = currentEv.event_key || currentEv.id;
        var r = await fetch('/api/calendar/notes?event_key=' + encodeURIComponent(key), {
            method: 'DELETE',
        });
        var data = await r.json();
        if (!r.ok) {
            alert(data.error || 'Ошибка');
            return;
        }
        qs('event-modal-note').value = '';
        syncNoteToCalendar(key, '');
        if (window.showToast) window.showToast(data.message || 'Заметка удалена');
        loadMeta(currentEv);
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
            enable_queue: qs('ev-slot-enable-queue') && qs('ev-slot-enable-queue').checked,
            enable_submission: qs('ev-slot-enable-submission') &&
                qs('ev-slot-enable-submission').checked,
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
        var r = await fetch('/appointment/cancel/' + currentEv.booking_id, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'csrf_token=' + encodeURIComponent(
                (document.querySelector('meta[name="csrf-token"]') || {}).content || '',
            ),
        });
        if (r.redirected) {
            window.location.href = r.url;
            return;
        }
        var data = await r.json().catch(function () { return {}; });
        if (!r.ok) {
            alert(data.error || 'Не удалось отменить запись');
            return;
        }
        if (window.showToast) window.showToast('Запись отменена');
        closeModal();
        window.location.reload();
    }

    async function uploadTeacherFile(fileInputId) {
        if (!currentEv) return;
        var fileInput = qs(fileInputId || 'event-modal-file');
        if (!fileInput || !fileInput.files.length) return;
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

    async function uploadSubmission() {
        if (!currentEv || !currentEv.slot_id) return;
        var fileInput = qs('event-modal-submission-file');
        if (!fileInput || !fileInput.files.length) return;
        var fd = new FormData();
        fd.append('file', fileInput.files[0]);
        var r = await fetch('/api/slots/' + currentEv.slot_id + '/submissions', {
            method: 'POST', body: fd,
        });
        var data = await r.json();
        if (data.ok) {
            if (window.showToast) window.showToast(data.message || 'Загружено');
            fileInput.value = '';
            loadMeta(currentEv);
        } else if (window.showToast) {
            window.showToast(data.error || 'Ошибка', 'error');
        }
    }

    async function joinQueue() {
        if (!currentEv || !currentEv.slot_id) return;
        var r = await fetch('/api/slots/' + currentEv.slot_id + '/queue', { method: 'POST' });
        var data = await r.json();
        if (data.ok) {
            if (window.showToast) window.showToast(data.message || 'В очереди');
            loadMeta(currentEv);
        } else if (window.showToast) {
            window.showToast(data.error || 'Ошибка', 'error');
        }
    }

    async function leaveQueue() {
        if (!currentEv || !currentEv.slot_id) return;
        var r = await fetch('/api/slots/' + currentEv.slot_id + '/queue', { method: 'DELETE' });
        var data = await r.json();
        if (data.ok) {
            if (window.showToast) window.showToast('Вы вышли из очереди');
            loadMeta(currentEv);
        } else if (window.showToast) {
            window.showToast(data.error || 'Ошибка', 'error');
        }
    }

    qs('event-modal-close').onclick = closeModal;
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });
    var editBtn = qs('event-modal-edit-btn');
    if (editBtn) {
        editBtn.onclick = function () {
            if (!canTeacherEdit(currentEv)) return;
            setEditMode(!editMode);
        };
    }
    qs('event-modal-save-note').onclick = saveNoteAndFiles;
    var deleteNoteBtn = qs('event-modal-delete-note');
    if (deleteNoteBtn) deleteNoteBtn.onclick = deleteNote;
    qs('ev-slot-save').onclick = function () { saveSlot(false); };
    qs('ev-slot-delete').onclick = deleteSlot;
    var cancelBookingBtn = qs('event-modal-cancel-booking');
    if (cancelBookingBtn) cancelBookingBtn.onclick = cancelBooking;
    var uploadBtn = qs('event-modal-upload-btn');
    if (uploadBtn) uploadBtn.onclick = function () { uploadTeacherFile('event-modal-file'); };
    var lessonUploadBtn = qs('event-modal-lesson-upload-btn');
    if (lessonUploadBtn) {
        lessonUploadBtn.onclick = function () { uploadTeacherFile('event-modal-lesson-file'); };
    }
    var subUp = qs('event-modal-submission-upload');
    if (subUp) subUp.onclick = uploadSubmission;
    var joinQ = qs('event-modal-join-queue');
    if (joinQ) joinQ.onclick = joinQueue;
    var leaveQ = qs('event-modal-leave-queue');
    if (leaveQ) leaveQ.onclick = leaveQueue;

    window.EventModal = {
        open: openModal,
        close: closeModal,
        openEdit: function (ev) { openModal(ev, { edit: true }); },
    };

    var sy = sessionStorage.getItem('scrollRestoreY');
    if (sy) {
        sessionStorage.removeItem('scrollRestoreY');
        window.scrollTo(0, parseInt(sy, 10) || 0);
    }
})();
