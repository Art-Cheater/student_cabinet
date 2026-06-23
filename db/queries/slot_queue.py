def join_queue(conn, slot_id, student_user_id):
    slot = conn.execute('SELECT enable_queue FROM office_slots WHERE id = %s', (slot_id,)).fetchone()
    if not slot or not slot.get('enable_queue'):
        return False, 'Очередь недоступна'
    existing = conn.execute('''
        SELECT id FROM office_queue_entries WHERE slot_id = %s AND student_user_id = %s
    ''', (slot_id, student_user_id)).fetchone()
    if existing:
        return False, 'Вы уже в очереди'
    max_pos = conn.execute('''
        SELECT COALESCE(MAX(position), 0) AS m FROM office_queue_entries WHERE slot_id = %s
    ''', (slot_id,)).fetchone()['m']
    conn.execute('''
        INSERT INTO office_queue_entries (slot_id, student_user_id, position)
        VALUES (%s, %s, %s)
    ''', (slot_id, student_user_id, max_pos + 1))
    return True, None


def leave_queue(conn, slot_id, student_user_id):
    cur = conn.execute('''
        DELETE FROM office_queue_entries
        WHERE slot_id = %s AND student_user_id = %s RETURNING id
    ''', (slot_id, student_user_id))
    if not cur.fetchone():
        return False, 'Вы не в очереди'
    _reindex_queue(conn, slot_id)
    return True, None


def _reindex_queue(conn, slot_id):
    rows = conn.execute('''
        SELECT id FROM office_queue_entries WHERE slot_id = %s ORDER BY position, created_at
    ''', (slot_id,)).fetchall()
    for i, row in enumerate(rows, start=1):
        conn.execute('UPDATE office_queue_entries SET position = %s WHERE id = %s', (i, row['id']))


def list_queue(conn, slot_id):
    return conn.execute('''
        SELECT q.id, q.position, q.created_at, q.passed_at,
               u.last_name, u.first_name, u.middle_name, g.name AS group_name,
               q.student_user_id
        FROM office_queue_entries q
        JOIN users u ON u.id = q.student_user_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE q.slot_id = %s
        ORDER BY q.position
    ''', (slot_id,)).fetchall()


def set_queue_passed(conn, entry_id, slot_id, teacher_user_id, passed):
    row = conn.execute('''
        SELECT q.id FROM office_queue_entries q
        JOIN office_slots os ON os.id = q.slot_id
        WHERE q.id = %s AND q.slot_id = %s AND os.teacher_user_id = %s
    ''', (entry_id, slot_id, teacher_user_id)).fetchone()
    if not row:
        return False, 'Запись не найдена'
    if passed:
        conn.execute(
            'UPDATE office_queue_entries SET passed_at = NOW() WHERE id = %s',
            (entry_id,),
        )
    else:
        conn.execute(
            'UPDATE office_queue_entries SET passed_at = NULL WHERE id = %s',
            (entry_id,),
        )
    return True, None


def get_queue_entry(conn, slot_id, student_user_id):
    return conn.execute('''
        SELECT * FROM office_queue_entries WHERE slot_id = %s AND student_user_id = %s
    ''', (slot_id, student_user_id)).fetchone()


def add_submission(conn, slot_id, student_user_id, stored_path, original_name):
    slot = conn.execute('SELECT enable_submission FROM office_slots WHERE id = %s', (slot_id,)).fetchone()
    if not slot or not slot.get('enable_submission'):
        return None, 'Сдача работ недоступна'
    cur = conn.execute('''
        INSERT INTO office_submissions (slot_id, student_user_id, stored_path, original_name)
        VALUES (%s, %s, %s, %s) RETURNING id
    ''', (slot_id, student_user_id, stored_path, original_name))
    return cur.fetchone()['id'], None


def list_submissions(conn, slot_id, student_user_id=None):
    sql = '''
        SELECT s.id, s.original_name, s.uploaded_at, s.student_user_id,
               u.last_name, u.first_name, u.middle_name, g.name AS group_name
        FROM office_submissions s
        JOIN users u ON u.id = s.student_user_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE s.slot_id = %s
    '''
    params = [slot_id]
    if student_user_id:
        sql += ' AND s.student_user_id = %s'
        params.append(student_user_id)
    sql += ' ORDER BY s.uploaded_at'
    return conn.execute(sql, params).fetchall()


def delete_submission(conn, submission_id, student_user_id):
    row = conn.execute('''
        SELECT stored_path FROM office_submissions
        WHERE id = %s AND student_user_id = %s
    ''', (submission_id, student_user_id)).fetchone()
    if not row:
        return None, 'Файл не найден'
    conn.execute('DELETE FROM office_submissions WHERE id = %s', (submission_id,))
    return row['stored_path'], None


def get_submission(conn, submission_id):
    return conn.execute('SELECT * FROM office_submissions WHERE id = %s', (submission_id,)).fetchone()
