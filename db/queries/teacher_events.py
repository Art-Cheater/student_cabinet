def create_personal_event(conn, teacher_user_id, event_date, time_start, time_end, title, color=None):
    cur = conn.execute('''
        INSERT INTO teacher_personal_events
        (teacher_user_id, event_date, time_start, time_end, title, color)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    ''', (teacher_user_id, event_date, time_start, time_end, title, color))
    return cur.fetchone()['id']


def list_personal_events(conn, teacher_user_id, date_from, date_to):
    return conn.execute('''
        SELECT * FROM teacher_personal_events
        WHERE teacher_user_id = %s AND event_date BETWEEN %s AND %s
        ORDER BY event_date, time_start
    ''', (teacher_user_id, date_from, date_to)).fetchall()


def delete_personal_event(conn, event_id, teacher_user_id):
    cur = conn.execute('''
        DELETE FROM teacher_personal_events
        WHERE id = %s AND teacher_user_id = %s RETURNING id
    ''', (event_id, teacher_user_id))
    return cur.fetchone() is not None
