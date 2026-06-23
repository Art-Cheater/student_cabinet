from db.queries.schedule import get_or_create_classroom, parse_room_display


def create_office_slot(conn, teacher_user_id, slot_date, time_start, time_end,
                       room_display, topic, max_students, audience_type, group_ids,
                       conflict_events=None, confirm_overlap=False,
                       enable_queue=False, enable_submission=False):
    if conflict_events is not None:
        from services.schedule_conflicts import hard_overlap, soft_overlap, conflict_message
        if hard_overlap(slot_date, time_start, time_end, conflict_events):
            raise ValueError(conflict_message())
        if not confirm_overlap and soft_overlap(
            slot_date, time_start, time_end, conflict_events,
        ):
            raise ValueError('LESSON_OVERLAP')
    classroom_id = None
    if room_display:
        classroom_id = get_or_create_classroom(conn, room_display)
    cur = conn.execute('''
        INSERT INTO office_slots
        (teacher_user_id, slot_date, time_start, time_end, classroom_id, room_display,
         topic, max_students, audience_type, enable_queue, enable_submission)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        teacher_user_id, slot_date, time_start, time_end,
        classroom_id, room_display, topic, max_students, audience_type,
        bool(enable_queue), bool(enable_submission),
    ))
    slot_id = cur.fetchone()['id']
    if audience_type in ('one_group', 'multi_group') and group_ids:
        for gid in group_ids:
            conn.execute(
                'INSERT INTO office_slot_groups (slot_id, group_id) VALUES (%s, %s)',
                (slot_id, gid),
            )
    return slot_id


def update_office_slot(conn, slot_id, teacher_user_id, fields, conflict_events=None,
                       confirm_overlap=False):
    slot = conn.execute(
        'SELECT * FROM office_slots WHERE id = %s AND teacher_user_id = %s',
        (slot_id, teacher_user_id),
    ).fetchone()
    if not slot:
        return False
    sd = fields.get('slot_date', slot['slot_date'])
    ts = fields.get('time_start', slot['time_start'])
    te = fields.get('time_end', slot['time_end'])
    if conflict_events is not None:
        from services.schedule_conflicts import hard_overlap, soft_overlap, conflict_message
        if hard_overlap(sd, ts, te, conflict_events, exclude_slot_id=slot_id):
            raise ValueError(conflict_message())
        if not confirm_overlap and soft_overlap(
            sd, ts, te, conflict_events, exclude_slot_id=slot_id,
        ):
            raise ValueError('LESSON_OVERLAP')
    room = fields.get('room_display', slot['room_display'])
    classroom_id = slot['classroom_id']
    if room:
        classroom_id = get_or_create_classroom(conn, room)
    enable_queue = fields.get('enable_queue', slot.get('enable_queue'))
    enable_submission = fields.get('enable_submission', slot.get('enable_submission'))
    if 'enable_queue' in fields:
        enable_queue = bool(fields['enable_queue'])
    if 'enable_submission' in fields:
        enable_submission = bool(fields['enable_submission'])
    conn.execute('''
        UPDATE office_slots SET
            slot_date = %s, time_start = %s, time_end = %s,
            classroom_id = %s, room_display = %s, topic = %s, max_students = %s,
            enable_queue = %s, enable_submission = %s
        WHERE id = %s AND teacher_user_id = %s
    ''', (
        sd, ts, te, classroom_id, room,
        fields.get('topic', slot['topic']),
        fields.get('max_students', slot['max_students']),
        enable_queue, enable_submission,
        slot_id, teacher_user_id,
    ))
    return True


def delete_office_slot(conn, slot_id, teacher_user_id):
    cur = conn.execute('''
        DELETE FROM office_slots WHERE id = %s AND teacher_user_id = %s RETURNING id
    ''', (slot_id, teacher_user_id))
    return cur.fetchone() is not None


def _coerce_group_id(group_id):
    if group_id is None or group_id == '':
        return None
    try:
        return int(group_id)
    except (TypeError, ValueError):
        return None


def _student_booking_on_slot(conn, slot_id, student_user_id):
    if not student_user_id:
        return None
    return conn.execute('''
        SELECT id, status FROM office_bookings
        WHERE slot_id = %s AND student_user_id = %s
    ''', (slot_id, student_user_id)).fetchone()


def _slot_allowed_groups(conn, slot_id):
    groups = conn.execute(
        'SELECT group_id FROM office_slot_groups WHERE slot_id = %s', (slot_id,),
    ).fetchall()
    allowed = {_coerce_group_id(g['group_id']) for g in groups}
    allowed.discard(None)
    return allowed


def _slot_audience_ok(conn, slot, student_group_id):
    """True if slot audience includes student_group_id (or slot is open to anyone)."""
    student_group_id = _coerce_group_id(student_group_id)
    at = slot['audience_type']
    if at == 'anyone':
        return True
    if not student_group_id:
        return False
    return student_group_id in _slot_allowed_groups(conn, slot['id'])


def get_available_slots_for_student(
    conn, teacher_user_id, student_group_id, date_from, date_to, student_user_id=None,
):
    student_group_id = _coerce_group_id(student_group_id)
    rows = conn.execute('''
        SELECT os.*, c.display_name AS classroom_display, b.number AS building_number,
               (SELECT COUNT(*) FROM office_bookings ob
                WHERE ob.slot_id = os.id AND ob.status IN ('pending', 'confirmed')) AS bookings_count
        FROM office_slots os
        LEFT JOIN classrooms c ON c.id = os.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE os.teacher_user_id = %s AND os.slot_date BETWEEN %s AND %s
        ORDER BY os.slot_date, os.time_start
    ''', (teacher_user_id, date_from, date_to)).fetchall()

    result = []
    for slot in rows:
        sb = _student_booking_on_slot(conn, slot['id'], student_user_id)
        if sb and sb['status'] in ('pending', 'confirmed'):
            continue
        if slot['bookings_count'] >= slot['max_students']:
            continue
        if not _slot_audience_ok(conn, slot, student_group_id):
            continue
        result.append(slot)
    return result


def get_teacher_slots(conn, teacher_user_id, date_from, date_to):
    return conn.execute('''
        SELECT os.*, c.display_name AS classroom_display, b.number AS building_number,
               (SELECT COUNT(*) FROM office_bookings ob
                WHERE ob.slot_id = os.id AND ob.status IN ('pending', 'confirmed')) AS bookings_count
        FROM office_slots os
        LEFT JOIN classrooms c ON c.id = os.classroom_id
        LEFT JOIN buildings b ON b.id = c.building_id
        WHERE os.teacher_user_id = %s AND os.slot_date BETWEEN %s AND %s
        ORDER BY os.slot_date, os.time_start
    ''', (teacher_user_id, date_from, date_to)).fetchall()


def create_booking(conn, slot_id, student_user_id, student_group_id=None):
    can_book, block_reason = student_can_book_slot(
        conn, slot_id, student_user_id, student_group_id,
    )
    if not can_book:
        return False, block_reason
    slot = conn.execute('SELECT * FROM office_slots WHERE id = %s', (slot_id,)).fetchone()
    if not slot:
        return False, 'Слот не найден'
    existing = conn.execute('''
        SELECT id, status FROM office_bookings
        WHERE slot_id = %s AND student_user_id = %s
    ''', (slot_id, student_user_id)).fetchone()
    if existing:
        if existing['status'] in ('pending', 'confirmed'):
            return False, 'Вы уже записаны'
        if existing['status'] == 'rejected':
            return False, 'Запись отклонена преподавателем. Обратитесь к преподавателю.'
        if existing['status'] == 'cancelled':
            conn.execute(
                "UPDATE office_bookings SET status = 'pending', created_at = NOW() WHERE id = %s",
                (existing['id'],),
            )
            return True, None
    conn.execute('''
        INSERT INTO office_bookings (slot_id, student_user_id, status)
        VALUES (%s, %s, 'pending')
    ''', (slot_id, student_user_id))
    return True, None


def list_slot_bookings(conn, slot_id):
    return conn.execute('''
        SELECT ob.id, ob.status, ob.created_at,
               u.last_name, u.first_name, u.middle_name,
               g.name AS group_name
        FROM office_bookings ob
        JOIN users u ON u.id = ob.student_user_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE ob.slot_id = %s
        ORDER BY ob.created_at
    ''', (slot_id,)).fetchall()


def list_teacher_bookings(conn, teacher_user_id):
    return conn.execute('''
        SELECT ob.id AS booking_id, ob.status, ob.created_at,
               os.slot_date, os.time_start, os.time_end, os.topic,
               u.last_name, u.first_name, u.middle_name,
               g.name AS group_name
        FROM office_bookings ob
        JOIN office_slots os ON os.id = ob.slot_id
        JOIN users u ON u.id = ob.student_user_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE os.teacher_user_id = %s
        ORDER BY os.slot_date DESC, os.time_start
    ''', (teacher_user_id,)).fetchall()


def update_booking_status(conn, booking_id, teacher_user_id, status):
    row = conn.execute('''
        SELECT ob.id, ob.status, ob.slot_id, os.max_students
        FROM office_bookings ob
        JOIN office_slots os ON os.id = ob.slot_id
        WHERE ob.id = %s AND os.teacher_user_id = %s
    ''', (booking_id, teacher_user_id)).fetchone()
    if not row:
        return False, 'Не найдено'
    if status == 'pending':
        if row['status'] == 'cancelled':
            return False, 'Студент отменил запись сам — он может записаться снова самостоятельно'
        if row['status'] != 'rejected':
            return False, 'Нельзя вернуть эту запись'
        cnt = conn.execute('''
            SELECT COUNT(*) AS c FROM office_bookings
            WHERE slot_id = %s AND status IN ('pending', 'confirmed') AND id != %s
        ''', (row['slot_id'], booking_id)).fetchone()['c']
        if cnt >= row['max_students']:
            return False, 'Мест нет'
    conn.execute(
        'UPDATE office_bookings SET status = %s WHERE id = %s',
        (status, booking_id),
    )
    return True, None


def list_teacher_slots_summary(conn, teacher_user_id, date_from=None, date_to=None):
    sql = '''
        SELECT os.id, os.slot_date, os.time_start, os.time_end, os.topic, os.room_display,
               os.max_students, os.audience_type,
               (SELECT COUNT(*) FROM office_bookings ob
                WHERE ob.slot_id = os.id AND ob.status IN ('pending', 'confirmed')) AS bookings_count
        FROM office_slots os
        WHERE os.teacher_user_id = %s
    '''
    params = [teacher_user_id]
    if date_from and date_to:
        sql += ' AND os.slot_date BETWEEN %s AND %s'
        params.extend([date_from, date_to])
    sql += ' ORDER BY os.slot_date DESC, os.time_start'
    return conn.execute(sql, params).fetchall()


def cancel_student_booking(conn, booking_id, student_user_id):
    row = conn.execute('''
        SELECT ob.id, ob.status FROM office_bookings ob
        WHERE ob.id = %s AND ob.student_user_id = %s
    ''', (booking_id, student_user_id)).fetchone()
    if not row:
        return False, 'Запись не найдена'
    if row['status'] not in ('pending', 'confirmed'):
        return False, 'Запись уже отменена'
    conn.execute(
        "UPDATE office_bookings SET status = 'cancelled' WHERE id = %s",
        (booking_id,),
    )
    return True, None


def list_student_bookings(conn, student_user_id):
    return conn.execute('''
        SELECT ob.id AS booking_id, ob.slot_id, ob.status, ob.created_at,
               os.slot_date, os.time_start, os.time_end, os.topic, os.room_display,
               u.last_name AS teacher_last_name, u.first_name AS teacher_first_name,
               u.middle_name AS teacher_middle_name,
               tp.position_title
        FROM office_bookings ob
        JOIN office_slots os ON os.id = ob.slot_id
        JOIN users u ON u.id = os.teacher_user_id
        LEFT JOIN teacher_profiles tp ON tp.user_id = u.id
        WHERE ob.student_user_id = %s
        ORDER BY os.slot_date DESC, os.time_start
    ''', (student_user_id,)).fetchall()


def student_slot_lesson_overlap(conn, group_name, slot_id):
    """Return warning text if slot overlaps student's lessons on that day."""
    from db.queries.schedule import get_schedule_events
    from services.schedule_conflicts import _overlaps_at

    slot = conn.execute(
        'SELECT slot_date, time_start, time_end FROM office_slots WHERE id = %s',
        (slot_id,),
    ).fetchone()
    if not slot or not group_name:
        return None
    sd = slot['slot_date']
    d = sd.isoformat()[:10] if hasattr(sd, 'isoformat') else str(sd)[:10]
    events = get_schedule_events(conn, group_name, d, d)
    overlap, ev = _overlaps_at(
        sd, slot['time_start'], slot['time_end'], events,
        types_allowed={'lesson'},
    )
    if overlap and ev:
        title = ev.get('title') or 'пара'
        return f'В это время у вас пара: {title}'
    return None


def student_can_book_slot(conn, slot_id, student_user_id, student_group_id=None):
    """Return (ok, error_message). error_message is None when ok."""
    student_group_id = _coerce_group_id(student_group_id)
    slot = conn.execute('SELECT * FROM office_slots WHERE id = %s', (slot_id,)).fetchone()
    if not slot:
        return False, 'Слот не найден'
    existing = conn.execute('''
        SELECT id, status FROM office_bookings
        WHERE slot_id = %s AND student_user_id = %s
    ''', (slot_id, student_user_id)).fetchone()
    if existing:
        if existing['status'] in ('pending', 'confirmed'):
            return False, 'Вы уже записаны'
        if existing['status'] == 'rejected':
            return False, 'Запись отклонена преподавателем. Обратитесь к преподавателю.'
        if existing['status'] == 'cancelled':
            pass
    cnt = conn.execute('''
        SELECT COUNT(*) AS c FROM office_bookings
        WHERE slot_id = %s AND status IN ('pending', 'confirmed')
    ''', (slot_id,)).fetchone()['c']
    if cnt >= slot['max_students']:
        if existing and existing['status'] == 'cancelled':
            return False, 'Мест нет — окно уже занято другими студентами'
        return False, 'Мест нет'
    at = slot['audience_type']
    if at == 'anyone':
        return True, None
    if not student_group_id:
        return False, 'Группа не указана в профиле. Обратитесь к администратору.'
    if student_group_id in _slot_allowed_groups(conn, slot_id):
        return True, None
    return False, 'Это окно недоступно для вашей группы'
