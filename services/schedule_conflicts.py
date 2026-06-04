from datetime import time


def _to_time(value):
    if value is None:
        return time(0, 0)
    if isinstance(value, time):
        return value
    s = str(value).strip().replace('.', ':')
    parts = s.split(':')
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _event_bounds(ev, slot_date):
    sd = slot_date
    if hasattr(sd, 'isoformat'):
        sd = sd.isoformat()[:10]
    else:
        sd = str(sd)[:10]
    start_s = ev.get('start') or ''
    end_s = ev.get('end') or start_s
    if len(start_s) < 10 or start_s[:10] != sd:
        return None, None
    if 'T' in start_s:
        start_t = start_s.split('T', 1)[1][:5]
    else:
        start_t = '09:00'
    if 'T' in end_s and end_s[:10] == sd:
        end_t = end_s.split('T', 1)[1][:5]
    else:
        end_t = start_t
    return _to_time(start_t), _to_time(end_t)


def _overlaps_at(slot_date, slot_start, slot_end, events, types_allowed, exclude_slot_id=None):
    t_start = _to_time(slot_start)
    t_end = _to_time(slot_end)
    if t_end <= t_start:
        t_end = time(t_start.hour + 1, t_start.minute)

    for ev in events:
        if exclude_slot_id and ev.get('slot_id') == exclude_slot_id:
            continue
        ev_type = ev.get('type', 'lesson')
        if types_allowed is not None and ev_type not in types_allowed:
            continue
        bounds = _event_bounds(ev, slot_date)
        if not bounds[0]:
            continue
        ev_start, ev_end = bounds
        if ev_end <= ev_start:
            ev_end = time(ev_start.hour + 1, ev_start.minute)
        if t_start < ev_end and t_end > ev_start:
            return True, ev
    return False, None


def hard_overlap(slot_date, slot_start, slot_end, events, exclude_slot_id=None):
    """Another office slot at the same time."""
    return _overlaps_at(
        slot_date, slot_start, slot_end, events,
        types_allowed={'office_slot'},
        exclude_slot_id=exclude_slot_id,
    )[0]


def soft_overlap(slot_date, slot_start, slot_end, events, exclude_slot_id=None):
    """Lesson or university event at the same time."""
    return _overlaps_at(
        slot_date, slot_start, slot_end, events,
        types_allowed={'lesson', 'university_lesson'},
        exclude_slot_id=exclude_slot_id,
    )[0]


def intervals_overlap(slot_date, slot_start, slot_end, events, exclude_slot_id=None):
    """Any overlap (hard + soft)."""
    h, _ = _overlaps_at(
        slot_date, slot_start, slot_end, events, types_allowed=None,
        exclude_slot_id=exclude_slot_id,
    )
    return h


def conflict_message():
    return 'В это время уже есть другой слот приёма.'


def soft_conflict_message():
    return 'В это время у вас пара (или занятие ВятГУ).'
