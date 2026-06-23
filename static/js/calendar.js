(function () {
    var HOUR_START = 9;
    var HOUR_END = 21;
    var DAY_NAMES = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
    var MONTH_NAMES = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];

    function getHourPx() {
        var v = getComputedStyle(document.documentElement).getPropertyValue('--cal-hour-h');
        return parseInt(v, 10) || 48;
    }

    function getHoursCount() {
        return HOUR_END - HOUR_START;
    }

    function formatLocalDate(d) {
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
    }

    function parseLocalDate(str) {
        var p = (str || '').split('-');
        return new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
    }

    function parseEventStart(ev) {
        var s = ev.start || '';
        var p = s.split('T');
        if (p.length < 2) return parseLocalDate(p[0]);
        var t = p[1].split(':');
        return new Date(
            parseInt(p[0].split('-')[0], 10),
            parseInt(p[0].split('-')[1], 10) - 1,
            parseInt(p[0].split('-')[2], 10),
            parseInt(t[0], 10) || 0,
            parseInt(t[1], 10) || 0
        );
    }

    function eventOnLocalDay(ev, dayStr) {
        var s = ev.start || '';
        return s.slice(0, 10) === dayStr;
    }

    function minutesFromTime(d) {
        return d.getHours() * 60 + d.getMinutes();
    }

    function eventTypeClass(ev) {
        var t = ev.type || 'lesson';
        if (t === 'office_slot') return ' slot';
        if (t === 'booking') return ' booking';
        if (t === 'university_lesson') return ' university';
        if (t === 'personal') return ' personal';
        return ' lesson';
    }

    function eventRangeMinutes(ev) {
        var start = parseEventStart(ev);
        var end = parseEventStart(ev);
        if (ev.end) {
            var ep = ev.end.split('T');
            if (ep.length >= 2) {
                var et = ep[1].split(':');
                end = new Date(
                    parseInt(ep[0].split('-')[0], 10),
                    parseInt(ep[0].split('-')[1], 10) - 1,
                    parseInt(ep[0].split('-')[2], 10),
                    parseInt(et[0], 10) || 0,
                    parseInt(et[1], 10) || 0
                );
            }
        }
        var rangeStart = HOUR_START * 60;
        var rangeEnd = HOUR_END * 60;
        var sm = Math.max(minutesFromTime(start), rangeStart);
        var em = Math.min(minutesFromTime(end), rangeEnd);
        if (em <= sm) em = sm + 45;
        return { ev: ev, sm: sm, em: em };
    }

    function assignOverlapLanes(ranges) {
        var sorted = ranges.slice().sort(function (a, b) {
            return a.sm - b.sm || (b.em - b.sm) - (a.em - a.sm);
        });
        var clusters = [];
        sorted.forEach(function (item) {
            var cluster = null;
            for (var i = 0; i < clusters.length; i++) {
                var c = clusters[i];
                if (item.sm < c.maxEnd) {
                    cluster = c;
                    break;
                }
            }
            if (!cluster) {
                cluster = { items: [], maxEnd: 0, lanes: [] };
                clusters.push(cluster);
            }
            cluster.items.push(item);
            cluster.maxEnd = Math.max(cluster.maxEnd, item.em);
        });
        clusters.forEach(function (cluster) {
            cluster.lanes = [];
            cluster.items.forEach(function (item) {
                var lane = 0;
                for (; lane < cluster.lanes.length; lane++) {
                    if (cluster.lanes[lane] <= item.sm) break;
                }
                if (lane === cluster.lanes.length) cluster.lanes.push(0);
                cluster.lanes[lane] = item.em;
                item.lane = lane;
                item.laneCount = 0;
            });
            var maxLane = 0;
            cluster.items.forEach(function (item) {
                if (item.lane + 1 > maxLane) maxLane = item.lane + 1;
            });
            cluster.items.forEach(function (item) {
                item.laneCount = maxLane;
            });
        });
        return sorted;
    }

    function clickOverlapKind(dayStr, hour, min, events) {
        var sm = hour * 60 + min;
        var em = sm + 45;
        var hard = false;
        var soft = false;
        for (var i = 0; i < events.length; i++) {
            var ev = events[i];
            if (!eventOnLocalDay(ev, dayStr)) continue;
            var start = parseEventStart(ev);
            var end = parseEventStart(ev);
            if (ev.end) {
                var ep = ev.end.split('T');
                if (ep.length >= 2) {
                    var et = ep[1].split(':');
                    end = new Date(
                        parseInt(ep[0].split('-')[0], 10),
                        parseInt(ep[0].split('-')[1], 10) - 1,
                        parseInt(ep[0].split('-')[2], 10),
                        parseInt(et[0], 10) || 0,
                        parseInt(et[1], 10) || 0
                    );
                }
            }
            var es = minutesFromTime(start);
            var ee = minutesFromTime(end);
            if (ee <= es) ee = es + 45;
            if (sm < ee && em > es) {
                var t = ev.type || 'lesson';
                if (t === 'office_slot') hard = true;
                else if (t === 'lesson' || t === 'university_lesson') soft = true;
                else soft = true;
            }
        }
        return { hard: hard, soft: soft };
    }

    function clickHitsEvent(dayStr, hour, min, events) {
        var k = clickOverlapKind(dayStr, hour, min, events);
        return k.hard || k.soft;
    }

    function placeEvents(col, events, dayStr) {
        col.querySelectorAll('.calendar-event').forEach(function (el) { el.remove(); });
        var body = col.querySelector('.day-body');
        if (!body) return;
        var hourPx = getHourPx();
        var rangeStart = HOUR_START * 60;
        var rangeEnd = HOUR_END * 60;
        var totalPx = getHoursCount() * hourPx;

        var dayEvents = events.filter(function (ev) { return eventOnLocalDay(ev, dayStr); });
        var ranges = dayEvents.map(eventRangeMinutes);
        assignOverlapLanes(ranges);
        var userRole = document.body.dataset.userRole || '';
        ranges.forEach(function (item) {
            var ev = item.ev;
            var sm = item.sm;
            var em = item.em;
            var top = ((sm - rangeStart) / (rangeEnd - rangeStart)) * totalPx;
            var height = Math.max(((em - sm) / (rangeEnd - rangeStart)) * totalPx, 24);
            var laneCount = item.laneCount || 1;
            var lane = item.lane || 0;
            var isSlot = ev.type === 'office_slot';
            var widthPct = (100 / laneCount);
            if (isSlot && laneCount > 1) widthPct = Math.min(widthPct, 38);
            var leftPct = lane * (100 / laneCount);
            if (isSlot && laneCount > 1) {
                leftPct = Math.max(0, 100 - widthPct - 2);
            }
            var div = document.createElement('div');
            var noteKey = ev.event_key || ev.id;
            div.className = 'calendar-event' + eventTypeClass(ev);
            if (laneCount > 1) div.classList.add('calendar-event--lane');
            div.dataset.eventKey = noteKey || '';
            div.style.top = top + 'px';
            div.style.height = height + 'px';
            div.style.left = 'calc(' + leftPct + '% + 2px)';
            div.style.width = 'calc(' + widthPct + '% - 4px)';
            div.style.right = 'auto';
            var room = ev.classroom || '';
            var bLink = ev.building_number
                ? '<a href="/map?building=' + ev.building_number + '">' + room + '</a>'
                : (room ? room : '');
            var notesMap = window.calendarNotesMap || {};
            var noteText = notesMap[noteKey] || '';
            var noteHtml = '';
            if (noteText) {
                if (noteText.length <= 48) {
                    noteHtml = '<div class="calendar-event-note">' + noteText.replace(/</g, '&lt;') + '</div>';
                } else {
                    noteHtml = '<div class="calendar-event-note calendar-event-note--hint" title="' +
                        noteText.replace(/"/g, '&quot;').replace(/</g, '&lt;') + '">📝 заметка</div>';
                }
            }
            var editBtn = '';
            div.innerHTML =
                '<div>' + (ev.start || '').slice(11, 16) + ' – ' + (ev.end || '').slice(11, 16) + '</div>' +
                (bLink ? '<div>' + bLink + '</div>' : '') +
                '<div><strong>' + (ev.title || '') + '</strong></div>' +
                (ev.teacher ? '<div>' + ev.teacher + '</div>' : '') +
                noteHtml;
            if (ev.slot_id) div.dataset.slotId = String(ev.slot_id);
            div.addEventListener('click', function (e) {
                if (e.target.closest('.calendar-event-edit')) return;
                e.stopPropagation();
                if (window.EventModal && window.EventModal.open) {
                    window.EventModal.open(ev);
                } else if (window.onCalendarEventClick) {
                    window.onCalendarEventClick(ev, div);
                }
            });
            body.appendChild(div);
        });
    }

    function buildTimeColumn(grid) {
        var timeCol = document.createElement('div');
        timeCol.className = 'time-col';
        var corner = document.createElement('div');
        corner.className = 'day-header';
        timeCol.appendChild(corner);
        var hourPx = getHourPx();
        for (var h = HOUR_START; h < HOUR_END; h++) {
            var tl = document.createElement('div');
            tl.className = 'time-label';
            tl.style.height = hourPx + 'px';
            tl.textContent = (h < 10 ? '0' : '') + h + ':00';
            timeCol.appendChild(tl);
        }
        grid.appendChild(timeCol);
        return hourPx;
    }

    function buildDayBody(col, dayStr, hourPx, allEvents) {
        var body = document.createElement('div');
        body.className = 'day-body';
        body.dataset.date = dayStr;
        if (window.CALENDAR_CLICKABLE) {
            body.dataset.clickable = 'true';
        }
        for (var hh = HOUR_START; hh < HOUR_END; hh++) {
            var line = document.createElement('div');
            line.className = 'hour-line';
            line.style.top = ((hh - HOUR_START) * hourPx) + 'px';
            body.appendChild(line);
        }
        if (window.CALENDAR_CLICKABLE) {
            body.addEventListener('click', function (e) {
                if (e.target.closest('.calendar-event')) return;
                var rect = body.getBoundingClientRect();
                var y = e.clientY - rect.top;
                var total = getHoursCount() * hourPx;
                var minutes = HOUR_START * 60 + (y / total) * (HOUR_END - HOUR_START) * 60;
                var hour = Math.min(HOUR_END - 1, Math.floor(minutes / 60));
                var min = Math.floor(minutes % 60 / 15) * 15;
                var overlap = clickOverlapKind(dayStr, hour, min, allEvents || []);
                if (overlap.hard) {
                    alert('В это время уже есть другой слот приёма.');
                    return;
                }
                window.slotConfirmOverlap = false;
                if (overlap.soft) {
                    if (!confirm('В это время у вас пара. Создать окно приёма всё равно?')) {
                        return;
                    }
                    window.slotConfirmOverlap = true;
                }
                if (window.openCalendarCellClick) {
                    window.openCalendarCellClick(dayStr, hour, min);
                } else if (window.openSlotModal) {
                    window.openSlotModal(dayStr, hour, min);
                }
            });
        }
        col.appendChild(body);
        return body;
    }

    function buildWeekGrid(root, events, weekStartStr, dayOnly) {
        var grid = root.querySelector('.calendar-grid');
        if (!grid) return;
        grid.innerHTML = '';
        grid.classList.remove('month-view');
        var weekStart = parseLocalDate(weekStartStr);
        var days = [];
        var count = dayOnly ? 1 : 7;
        if (dayOnly) {
            days.push(parseLocalDate(dayOnly));
        } else {
            for (var i = 0; i < 7; i++) {
                var d = new Date(weekStart);
                d.setDate(d.getDate() + i);
                days.push(d);
            }
        }
        grid.classList.toggle('day-view', count === 1);
        grid.style.gridTemplateColumns = '56px repeat(' + count + ', minmax(80px, 1fr))';

        var hourPx = buildTimeColumn(grid);
        days.forEach(function (d, idx) {
            var dayStr = formatLocalDate(d);
            var col = document.createElement('div');
            col.className = 'day-col';
            var hdr = document.createElement('div');
            hdr.className = 'day-header';
            var wd = d.getDay();
            var di = wd === 0 ? 6 : wd - 1;
            hdr.textContent = DAY_NAMES[di] + ' ' + d.getDate();
            col.appendChild(hdr);
            buildDayBody(col, dayStr, hourPx, events);
            grid.appendChild(col);
            placeEvents(col, events, dayStr);
        });
    }

    function buildMonthGrid(root, events, monthStr) {
        var grid = root.querySelector('.calendar-grid');
        if (!grid) return;
        grid.innerHTML = '';
        grid.classList.add('month-view');
        grid.classList.remove('day-view');
        grid.style.gridTemplateColumns = '';

        var parts = monthStr.split('-');
        var y = parseInt(parts[0], 10);
        var m = parseInt(parts[1], 10) - 1;
        var first = new Date(y, m, 1);
        var startPad = (first.getDay() + 6) % 7;
        var daysInMonth = new Date(y, m + 1, 0).getDate();

        var wrap = document.createElement('div');
        wrap.className = 'calendar-month';
        DAY_NAMES.forEach(function (n) {
            var h = document.createElement('div');
            h.className = 'month-weekday';
            h.textContent = n;
            wrap.appendChild(h);
        });
        for (var i = 0; i < startPad; i++) {
            var empty = document.createElement('div');
            empty.className = 'month-day other';
            wrap.appendChild(empty);
        }
        for (var d = 1; d <= daysInMonth; d++) {
            var cell = document.createElement('div');
            cell.className = 'month-day';
            var dayStr = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
            var link = document.createElement('a');
            link.href = '#';
            link.className = 'month-day-num';
            link.textContent = String(d);
            link.dataset.day = dayStr;
            link.addEventListener('click', function (e) {
                e.preventDefault();
                var day = this.dataset.day;
                if (window.calendarGoDay) window.calendarGoDay(day);
            });
            cell.appendChild(link);
            var dayEvents = events.filter(function (ev) { return eventOnLocalDay(ev, dayStr); });
            dayEvents.slice(0, 3).forEach(function (ev) {
                var sp = document.createElement('div');
                sp.className = 'month-event';
                sp.textContent = (ev.start || '').slice(11, 16) + ' ' + (ev.title || '');
                cell.appendChild(sp);
            });
            if (dayEvents.length > 3) {
                var more = document.createElement('div');
                more.className = 'month-event-more';
                more.textContent = '+' + (dayEvents.length - 3);
                cell.appendChild(more);
            }
            wrap.appendChild(cell);
        }
        grid.appendChild(wrap);
    }

    function loadEvents() {
        var el = document.getElementById('calendar-events');
        if (!el) return [];
        try {
            return JSON.parse(el.textContent || '[]');
        } catch (e) {
            return [];
        }
    }

    function loadNotesMap() {
        var el = document.getElementById('calendar-notes');
        if (!el) return {};
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (e) {
            return {};
        }
    }

    function showCalendarSkeleton(root) {
        root.classList.add('is-loading');
        var sk = document.createElement('div');
        sk.className = 'calendar-skeleton';
        sk.setAttribute('aria-hidden', 'true');
        sk.innerHTML = '<div class="skeleton skeleton-grid"></div>';
        root.appendChild(sk);
    }

    function hideCalendarSkeleton(root) {
        root.classList.remove('is-loading');
        var sk = root.querySelector('.calendar-skeleton');
        if (sk) sk.remove();
    }

    function init() {
        var root = document.getElementById('calendar-root');
        if (!root) return;
        showCalendarSkeleton(root);
        window.calendarNotesMap = loadNotesMap();
        var events = loadEvents();
        var view = root.dataset.view || 'week';
        var weekStart = root.dataset.weekStart || formatLocalDate(new Date());
        var day = root.dataset.day || '';
        var month = root.dataset.month || weekStart.slice(0, 7);

        if (view === 'month') {
            buildMonthGrid(root, events, month);
        } else if (view === 'day') {
            buildWeekGrid(root, events, weekStart, day || weekStart);
        } else {
            buildWeekGrid(root, events, weekStart, null);
        }
        window.setTimeout(function () {
            hideCalendarSkeleton(root);
        }, 150);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.CalendarGrid = {
        init: init,
        formatLocalDate: formatLocalDate,
        buildWeekGrid: buildWeekGrid,
        buildMonthGrid: buildMonthGrid,
    };
})();
