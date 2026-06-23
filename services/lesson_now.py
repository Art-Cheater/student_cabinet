"""Check if student's group is currently in a lesson."""
from datetime import date, datetime, time as dt_time

def student_in_lesson_now(conn, group_name, teacher_user_id=None, at=None):
    """Return active lesson event dict or None if group has no lesson right now."""
    if not group_name:
        return None
    now = at or datetime.now()
    today = now.date()
    from db.queries.schedule import get_schedule_events

    events = get_schedule_events(conn, group_name, today.isoformat(), today.isoformat())
    if not events:
        return None
    now_min = now.hour * 60 + now.minute
    for ev in events:
        start_s = (ev.get('start') or '')[11:16]
        end_s = (ev.get('end') or '')[11:16]
        if not start_s or not end_s:
            continue
        sh, sm = map(int, start_s.split(':'))
        eh, em = map(int, end_s.split(':'))
        if sh * 60 + sm <= now_min < eh * 60 + em:
            if teacher_user_id:
                from db.queries.users import get_teacher_profile
                prof = get_teacher_profile(conn, teacher_user_id)
                st_id = prof.get('schedule_teacher_id') if prof else None
                if st_id and ev.get('schedule_teacher_id') and ev['schedule_teacher_id'] != st_id:
                    continue
            return ev
    return None


def can_join_queue_now(conn, slot_id, student_user_id):
    from db.queries.users import get_student_profile

    slot = conn.execute(
        'SELECT * FROM office_slots WHERE id = %s', (slot_id,),
    ).fetchone()
    if not slot or not slot.get('enable_queue'):
        return False, 'Очередь не включена'
    prof = get_student_profile(conn, student_user_id)
    if not prof or not prof.get('group_name'):
        return False, 'Группа не указана'
    at = slot['audience_type']
    if at != 'anyone':
        groups = conn.execute(
            'SELECT group_id FROM office_slot_groups WHERE slot_id = %s', (slot_id,)
        ).fetchall()
        allowed = {g['group_id'] for g in groups}
        if prof.get('group_id') not in allowed:
            return False, 'Слот недоступен для вашей группы'
    return True, None
