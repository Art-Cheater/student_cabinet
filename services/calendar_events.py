import hashlib
import re
from datetime import date, timedelta


def make_event_key(event_type, **kwargs):
    if event_type == 'office_slot' and kwargs.get('slot_id'):
        return f'slot:{kwargs["slot_id"]}'
    if event_type == 'lesson' and kwargs.get('lesson_id') and kwargs.get('event_date'):
        return f'lesson:{kwargs["lesson_id"]}:{kwargs["event_date"]}'
    if event_type == 'booking' and kwargs.get('booking_id'):
        return f'booking:{kwargs["booking_id"]}'
    if event_type == 'university_lesson' and kwargs.get('start'):
        title = kwargs.get('title', '')
        h = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
        return f'uni:{kwargs["start"][:10]}:{h}'
    return kwargs.get('fallback_id') or f'{event_type}:unknown'

DAY_INDEX = {
    'Понедельник': 0, 'Вторник': 1, 'Среда': 2, 'Четверг': 3,
    'Пятница': 4, 'Суббота': 5, 'Воскресенье': 6,
}


def week_start_on(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d - timedelta(days=d.weekday())


def effective_week_start(effective_from):
    if effective_from:
        if isinstance(effective_from, str):
            effective_from = date.fromisoformat(effective_from[:10])
        return week_start_on(effective_from)
    return week_start_on(date.today())


def parse_time(t):
    if not t:
        return '09:00'
    t = str(t).strip().replace('.', ':')
    if len(t) >= 5:
        return t[:5]
    return t


def _lesson_date_from_day_name(day_name, ref_year):
    """Parse 'Вторник   02.06' or '02.06' from Excel day column."""
    day_name = (day_name or '').strip()
    m = re.search(r'(\d{1,2})\.(\d{1,2})', day_name)
    if m:
        day_num = int(m.group(1))
        month_num = int(m.group(2))
        try:
            return date(ref_year, month_num, day_num)
        except ValueError:
            return None
    for name, idx in DAY_INDEX.items():
        if name.lower() in day_name.lower():
            return None  # weekday only — resolved per target day in expand
    return None


def lesson_matches_date(lesson, d):
    day_name = (lesson.get('day_name') or lesson.get('day_of_week') or '').strip()
    explicit = _lesson_date_from_day_name(day_name, d.year)
    if explicit:
        return explicit == d
    for name, idx in DAY_INDEX.items():
        if name.lower() in day_name.lower():
            return idx == d.weekday()
    return False


def expand_lessons_to_events(lessons, effective_from, date_from, date_to):
    if isinstance(date_from, str):
        date_from = date.fromisoformat(date_from[:10])
    if isinstance(date_to, str):
        date_to = date.fromisoformat(date_to[:10])

    events = []
    d = date_from
    while d <= date_to:
        for lesson in lessons:
            if not lesson_matches_date(lesson, d):
                continue
            start = parse_time(lesson.get('time_start') or lesson.get('start_time'))
            end = parse_time(lesson.get('time_end') or lesson.get('end_time')) or start
            classroom = lesson.get('classroom') or lesson.get('display_name') or ''
            lid = lesson.get('lesson_id')
            ev = {
                'id': f'lesson-{d.isoformat()}-{start}-{lesson.get("subject", "")}',
                'title': lesson.get('subject') or lesson.get('discipline'),
                'start': f'{d.isoformat()}T{start}:00',
                'end': f'{d.isoformat()}T{end}:00',
                'type': 'lesson',
                'teacher': lesson.get('teacher'),
                'classroom': classroom,
                'building_number': lesson.get('building_number'),
                'lesson_type': lesson.get('lesson_type'),
                'lesson_id': lid,
            }
            ev['event_key'] = make_event_key(
                'lesson', lesson_id=lid, event_date=d.isoformat(),
                fallback_id=ev['id'],
            )
            events.append(ev)
        d += timedelta(days=1)
    return events


def group_slots_by_date(slots):
    """Group office slots by slot_date (ISO string keys, sorted)."""
    by_date = {}
    for slot in slots:
        sd = slot['slot_date']
        if hasattr(sd, 'isoformat'):
            key = sd.isoformat()[:10]
        else:
            key = str(sd)[:10]
        by_date.setdefault(key, []).append(slot)
    for key in by_date:
        by_date[key].sort(key=lambda s: str(s.get('time_start', '')))
    return dict(sorted(by_date.items()))


def first_slot_week_start(slots):
    if not slots:
        return None
    sd = slots[0]['slot_date']
    if hasattr(sd, 'isoformat'):
        d = sd if isinstance(sd, date) else date.fromisoformat(str(sd)[:10])
    else:
        d = date.fromisoformat(str(sd)[:10])
    return week_start_on(d).isoformat()


def booking_to_event(booking):
    start = booking['time_start']
    end = booking['time_end']
    if hasattr(start, 'isoformat'):
        start = start.isoformat()[:5]
    else:
        start = str(start)[:5]
    if hasattr(end, 'isoformat'):
        end = end.isoformat()[:5]
    else:
        end = str(end)[:5]
    sd = booking['slot_date']
    if hasattr(sd, 'isoformat'):
        sd = sd.isoformat()[:10]
    else:
        sd = str(sd)[:10]
    teacher = ' '.join(filter(None, [
        booking.get('teacher_last_name'),
        booking.get('teacher_first_name'),
        booking.get('teacher_middle_name'),
    ])).strip()
    topic = booking.get('topic') or 'Приём'
    bid = booking.get('booking_id', booking.get('id'))
    sid = booking.get('slot_id')
    ev = {
        'id': f'booking-{bid}',
        'title': f'{topic} ({teacher})' if teacher else topic,
        'start': f'{sd}T{start}:00',
        'end': f'{sd}T{end}:00',
        'type': 'booking',
        'classroom': booking.get('room_display') or '',
        'teacher': teacher,
        'status': booking.get('status'),
        'booking_id': bid,
        'slot_id': sid,
    }
    ev['event_key'] = make_event_key('booking', booking_id=bid, fallback_id=ev['id'])
    return ev


def slot_to_event(slot):
    start = slot['time_start']
    end = slot['time_end']
    if hasattr(start, 'isoformat'):
        start = start.isoformat()[:5]
    if hasattr(end, 'isoformat'):
        end = end.isoformat()[:5]
    sd = slot['slot_date']
    if hasattr(sd, 'isoformat'):
        sd = sd.isoformat()[:10]
    sid = slot['id']
    ev = {
        'id': f'slot-{sid}',
        'title': slot.get('topic') or 'Приём',
        'start': f'{sd}T{start}:00',
        'end': f'{sd}T{end}:00',
        'type': 'office_slot',
        'classroom': slot.get('room_display') or slot.get('classroom_display'),
        'building_number': slot.get('building_number'),
        'slot_id': sid,
        'bookings_count': slot.get('bookings_count', 0),
        'max_students': slot['max_students'],
    }
    ev['event_key'] = make_event_key('office_slot', slot_id=sid, fallback_id=ev['id'])
    return ev
