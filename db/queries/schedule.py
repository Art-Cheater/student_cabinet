import re

from db.queries.groups import get_or_create_group


def get_or_create_schedule_teacher(conn, name):
    name = (name or '').strip()
    if not name:
        return None
    row = conn.execute(
        'SELECT id FROM schedule_teachers WHERE name = %s', (name,)
    ).fetchone()
    if row:
        return row['id']
    cur = conn.execute(
        'INSERT INTO schedule_teachers (name) VALUES (%s) RETURNING id', (name,)
    )
    return cur.fetchone()['id']


def parse_room_display(room_text):
    """Parse '5-104' or '5 - 104' into (building_number, room_suffix, display)."""
    value = (room_text or '').strip()
    if not value:
        return None, None, None
    m = re.match(r'^(\d+)\s*[-–]\s*(\S+)', value)
    if m:
        display = f'{m.group(1)}-{m.group(2)}'
        return int(m.group(1)), m.group(2), display
    return None, None, value


def get_or_create_classroom(conn, room_text):
    room_text = (room_text or '').strip()
    if not room_text:
        return None
    building_num, room_suffix, display = parse_room_display(room_text)
    if not display:
        return None
    row = conn.execute(
        'SELECT id FROM classrooms WHERE display_name = %s', (display,)
    ).fetchone()
    if row:
        return row['id']
    building_id = None
    if building_num is not None:
        b = conn.execute(
            'SELECT id FROM buildings WHERE number = %s AND kind = %s',
            (building_num, 'building'),
        ).fetchone()
        if b:
            building_id = b['id']
    cur = conn.execute('''
        INSERT INTO classrooms (building_id, room_suffix, display_name)
        VALUES (%s, %s, %s) RETURNING id
    ''', (building_id, room_suffix, display))
    return cur.fetchone()['id']


def clear_schedule_for_upload(conn):
    conn.execute('DELETE FROM lessons')
    conn.execute('DELETE FROM uploads')


def insert_upload(conn, filename, effective_from=None, source='manual', vk_post_id=None):
    cur = conn.execute('''
        INSERT INTO uploads (filename, effective_from, source, vk_post_id)
        VALUES (%s, %s, %s, %s) RETURNING id
    ''', (filename, effective_from, source, vk_post_id))
    return cur.fetchone()['id']


def insert_lesson(conn, upload_id, group_id, schedule_teacher_id, classroom_id,
                  day_name, lesson_number, time_start, time_end, subject, lesson_type):
    conn.execute('''
        INSERT INTO lessons (
            upload_id, group_id, schedule_teacher_id, classroom_id,
            day_name, lesson_number, time_start, time_end, subject, lesson_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        upload_id, group_id, schedule_teacher_id, classroom_id,
        day_name, lesson_number, time_start, time_end, subject, lesson_type,
    ))


def get_latest_effective_from(conn):
    row = conn.execute('''
        SELECT effective_from FROM uploads
        WHERE effective_from IS NOT NULL
        ORDER BY uploaded_at DESC LIMIT 1
    ''').fetchone()
    return row['effective_from'] if row else None


def get_group_schedule(conn, group_name, filter_mode='week'):
    """Return lessons for a group (list view)."""
    from datetime import datetime, timedelta

    query = '''
        SELECT l.day_name AS day_of_week, l.time_start AS start_time, l.time_end AS end_time,
               l.subject AS discipline, l.lesson_type,
               st.name AS teacher, c.display_name AS classroom,
               b.number AS building_number
        FROM lessons l
        JOIN groups g ON g.id = l.group_id
        LEFT JOIN schedule_teachers st ON st.id = l.schedule_teacher_id
        LEFT JOIN classrooms c ON c.id = l.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE g.name = %s
        ORDER BY l.day_name, l.lesson_number
    '''
    rows = conn.execute(query, (group_name,)).fetchall()
    if filter_mode == 'week':
        return rows

    day_index = {
        'Понедельник': 0, 'Вторник': 1, 'Среда': 2, 'Четверг': 3,
        'Пятница': 4, 'Суббота': 5, 'Воскресенье': 6,
    }
    weekdays_ru = list(day_index.keys())
    today = datetime.now()
    if filter_mode == 'tomorrow':
        target = weekdays_ru[(today.weekday() + 1) % 7]
    else:
        target = weekdays_ru[today.weekday()]
    return [r for r in rows if r['day_of_week'] == target]


def get_schedule_events(conn, group_name, date_from, date_to):
    """Calendar events for group between dates."""
    from services.calendar_events import expand_lessons_to_events

    if not group_name:
        return []

    rows = conn.execute('''
        SELECT l.id AS lesson_id, l.day_name, l.time_start, l.time_end, l.subject, l.lesson_type,
               st.name AS teacher, c.display_name AS classroom,
               b.number AS building_number
        FROM lessons l
        JOIN groups g ON g.id = l.group_id
        LEFT JOIN schedule_teachers st ON st.id = l.schedule_teacher_id
        LEFT JOIN classrooms c ON c.id = l.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE g.name = %s
    ''', (group_name,)).fetchall()
    effective_from = get_latest_effective_from(conn)
    return expand_lessons_to_events(rows, effective_from, date_from, date_to)


def list_schedule_teacher_names(conn):
    return conn.execute(
        'SELECT id, name FROM schedule_teachers ORDER BY name'
    ).fetchall()


def get_teacher_lesson_events(conn, schedule_teacher_id, date_from, date_to):
    from services.calendar_events import expand_lessons_to_events

    if not schedule_teacher_id:
        return []
    rows = conn.execute('''
        SELECT l.id AS lesson_id, l.day_name, l.time_start, l.time_end, l.subject, l.lesson_type,
               st.name AS teacher, c.display_name AS classroom,
               b.number AS building_number
        FROM lessons l
        LEFT JOIN schedule_teachers st ON st.id = l.schedule_teacher_id
        LEFT JOIN classrooms c ON c.id = l.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE l.schedule_teacher_id = %s
    ''', (schedule_teacher_id,)).fetchall()
    effective_from = get_latest_effective_from(conn)
    return expand_lessons_to_events(rows, effective_from, date_from, date_to)


def get_classroom_events(conn, classroom_id, date_from, date_to, viewer_teacher_user_id=None):
    """Lessons and office slots in a classroom for calendar view."""
    from services.calendar_events import expand_lessons_to_events, slot_to_event

    if not classroom_id:
        return []
    viewer_st_id = None
    if viewer_teacher_user_id:
        from db.queries.users import get_teacher_profile
        prof = get_teacher_profile(conn, viewer_teacher_user_id)
        if prof:
            viewer_st_id = prof.get('schedule_teacher_id')
    rows = conn.execute('''
        SELECT l.id AS lesson_id, l.schedule_teacher_id, l.day_name, l.time_start, l.time_end,
               l.subject, l.lesson_type,
               st.name AS teacher, c.display_name AS classroom,
               b.number AS building_number
        FROM lessons l
        LEFT JOIN schedule_teachers st ON st.id = l.schedule_teacher_id
        LEFT JOIN classrooms c ON c.id = l.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE l.classroom_id = %s
    ''', (classroom_id,)).fetchall()
    effective_from = get_latest_effective_from(conn)
    events = expand_lessons_to_events(rows, effective_from, date_from, date_to)
    for ev in events:
        if ev.get('type') == 'lesson':
            st_id = ev.get('schedule_teacher_id')
            ev['is_own_lesson'] = bool(
                viewer_st_id and st_id and st_id == viewer_st_id,
            )
    slots = conn.execute('''
        SELECT os.*, c.display_name AS classroom_display, b.number AS building_number,
               (SELECT COUNT(*) FROM office_bookings ob
                WHERE ob.slot_id = os.id AND ob.status IN ('pending', 'confirmed')) AS bookings_count
        FROM office_slots os
        LEFT JOIN classrooms c ON c.id = os.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE os.classroom_id = %s AND os.slot_date BETWEEN %s AND %s
        ORDER BY os.slot_date, os.time_start
    ''', (classroom_id, date_from, date_to)).fetchall()
    events.extend([slot_to_event(s) for s in slots])
    return events


def list_classrooms(conn):
    return conn.execute('''
        SELECT c.id, c.display_name, b.number AS building_number
        FROM classrooms c
        LEFT JOIN buildings b ON b.id = c.building_id
        ORDER BY b.number NULLS LAST, c.display_name
    ''').fetchall()
