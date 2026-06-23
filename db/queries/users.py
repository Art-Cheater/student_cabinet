def get_role_id(conn, code):
    row = conn.execute(
        'SELECT id FROM roles WHERE code = %s', (code,)
    ).fetchone()
    return row['id'] if row else None


def get_user_by_email(conn, email):
    return conn.execute('''
        SELECT u.*, r.code AS role_code, r.title AS role_title
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE LOWER(u.email) = LOWER(%s) AND u.is_active = TRUE
    ''', ((email or '').strip(),)).fetchone()


def get_user_by_id(conn, user_id):
    return conn.execute('''
        SELECT u.*, r.code AS role_code, r.title AS role_title
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.id = %s
    ''', (user_id,)).fetchone()


def create_admin_user(conn, email, password_hash, last_name, first_name, middle_name):
    role_id = get_role_id(conn, 'admin')
    conn.execute('''
        INSERT INTO users (email, password_hash, role_id, last_name, first_name, middle_name)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (email, password_hash, role_id, last_name, first_name, middle_name))


def create_student_user(conn, email, password_hash, last_name, first_name, middle_name,
                        group_id, student_id, course, card_fields):
    role_id = get_role_id(conn, 'student')
    cur = conn.execute('''
        INSERT INTO users (email, password_hash, role_id, last_name, first_name, middle_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (email, password_hash, role_id, last_name, first_name, middle_name))
    user_id = cur.fetchone()['id']
    conn.execute('''
        INSERT INTO student_profiles
        (user_id, group_id, student_id, course, card_number_hash, card_number_last4,
         face_photo_path, study_form, issue_date, course_number, verification_signature)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        user_id, group_id, student_id, course,
        card_fields['card_number_hash'], card_fields['card_number_last4'],
        card_fields.get('face_photo_path'), card_fields['study_form'],
        card_fields['issue_date'], card_fields['course_number'],
        card_fields.get('verification_signature'),
    ))
    return user_id


def create_teacher_user(conn, email, password_hash, last_name, first_name, middle_name,
                        position_title, office_room, schedule_teacher_id=None,
                        pass_number=None, department=None):
    role_id = get_role_id(conn, 'teacher')
    cur = conn.execute('''
        INSERT INTO users (email, password_hash, role_id, last_name, first_name, middle_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (email, password_hash, role_id, last_name, first_name, middle_name))
    user_id = cur.fetchone()['id']
    conn.execute('''
        INSERT INTO teacher_profiles
        (user_id, position_title, office_room, schedule_teacher_id, pass_number, department)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (user_id, position_title, office_room, schedule_teacher_id, pass_number, department))
    return user_id


def create_guard_user(conn, email, password_hash, last_name, first_name, middle_name):
    role_id = get_role_id(conn, 'guard')
    conn.execute('''
        INSERT INTO users (email, password_hash, role_id, last_name, first_name, middle_name)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (email, password_hash, role_id, last_name, first_name, middle_name))


def count_students_admin(conn, group_id=None, search_q=None):
    sql = '''
        SELECT COUNT(*) AS c
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.code = 'student'
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        WHERE 1=1
    '''
    params = []
    if group_id:
        sql += ' AND sp.group_id = %s'
        params.append(group_id)
    if search_q:
        sql += ''' AND (
            u.last_name ILIKE %s OR u.first_name ILIKE %s OR u.email ILIKE %s
        )'''
        like = f'%{search_q}%'
        params.extend([like, like, like])
    row = conn.execute(sql, params).fetchone()
    return row['c'] if row else 0


def list_students_admin(conn, group_id=None, search_q=None, limit=50, offset=0):
    sql = '''
        SELECT u.id AS user_id, u.email, u.last_name, u.first_name, u.middle_name,
               g.name AS group_name, sp.group_id, sp.student_id, sp.course,
               sp.card_number_last4, sp.study_form, sp.issue_date, sp.course_number,
               sp.face_photo_path, sp.pass_number
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.code = 'student'
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE 1=1
    '''
    params = []
    if group_id:
        sql += ' AND sp.group_id = %s'
        params.append(group_id)
    if search_q:
        sql += ''' AND (
            u.last_name ILIKE %s OR u.first_name ILIKE %s OR u.email ILIKE %s
        )'''
        like = f'%{search_q}%'
        params.extend([like, like, like])
    sql += ' ORDER BY g.name NULLS LAST, u.last_name, u.first_name LIMIT %s OFFSET %s'
    params.extend([limit, offset])
    return conn.execute(sql, params).fetchall()


def list_teachers_admin(conn):
    return conn.execute('''
        SELECT u.id AS user_id, u.email, u.last_name, u.first_name, u.middle_name,
               tp.position_title, tp.office_room, tp.schedule_teacher_id,
               tp.pass_number, tp.department,
               st.name AS schedule_teacher_name
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.code = 'teacher'
        LEFT JOIN teacher_profiles tp ON tp.user_id = u.id
        LEFT JOIN schedule_teachers st ON st.id = tp.schedule_teacher_id
        ORDER BY u.last_name, u.first_name
    ''').fetchall()


def list_guards_admin(conn):
    return conn.execute('''
        SELECT u.id AS user_id, u.email, u.last_name, u.first_name, u.middle_name
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.code = 'guard'
        ORDER BY u.last_name, u.first_name
    ''').fetchall()


def list_teachers_public(conn):
    return conn.execute('''
        SELECT u.id, u.last_name, u.first_name, u.middle_name,
               tp.position_title, tp.office_room, tp.pass_number, tp.department
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.code = 'teacher'
        JOIN teacher_profiles tp ON tp.user_id = u.id
        WHERE u.is_active = TRUE
        ORDER BY u.last_name, u.first_name
    ''').fetchall()


def get_teacher_profile(conn, user_id):
    return conn.execute('''
        SELECT u.id, u.last_name, u.first_name, u.middle_name, u.email,
               tp.position_title, tp.office_room, tp.schedule_teacher_id,
               tp.pass_number, tp.department,
               st.name AS schedule_teacher_name
        FROM users u
        LEFT JOIN teacher_profiles tp ON tp.user_id = u.id
        LEFT JOIN schedule_teachers st ON st.id = tp.schedule_teacher_id
        WHERE u.id = %s
    ''', (user_id,)).fetchone()


def get_teacher_public(conn, user_id):
    return conn.execute('''
        SELECT u.id, u.last_name, u.first_name, u.middle_name,
               tp.position_title, tp.office_room, tp.pass_number, tp.department
        FROM users u
        JOIN teacher_profiles tp ON tp.user_id = u.id
        WHERE u.id = %s AND u.is_active = TRUE
    ''', (user_id,)).fetchone()


def update_student(conn, user_id, email, last_name, first_name, middle_name,
                   group_id, student_id, course, card_fields):
    conn.execute('''
        UPDATE users
        SET email = %s, last_name = %s, first_name = %s, middle_name = %s
        WHERE id = %s
    ''', (email, last_name, first_name, middle_name, user_id))
    conn.execute('''
        UPDATE student_profiles
        SET group_id = %s, student_id = %s, course = %s,
            card_number_hash = %s, card_number_last4 = %s,
            face_photo_path = COALESCE(%s, face_photo_path),
            study_form = %s, issue_date = %s, course_number = %s,
            verification_signature = NULL
        WHERE user_id = %s
    ''', (
        group_id, student_id, course,
        card_fields['card_number_hash'], card_fields['card_number_last4'],
        card_fields.get('face_photo_path'),
        card_fields['study_form'], card_fields['issue_date'], card_fields['course_number'],
        user_id,
    ))


def update_teacher(conn, user_id, email, last_name, first_name, middle_name,
                   position_title, office_room, schedule_teacher_id,
                   pass_number=None, department=None):
    conn.execute('''
        UPDATE users
        SET email = %s, last_name = %s, first_name = %s, middle_name = %s
        WHERE id = %s
    ''', (email, last_name, first_name, middle_name, user_id))
    conn.execute('''
        UPDATE teacher_profiles
        SET position_title = %s, office_room = %s, schedule_teacher_id = %s,
            pass_number = %s, department = %s
        WHERE user_id = %s
    ''', (position_title, office_room, schedule_teacher_id, pass_number, department, user_id))


def update_student_pass_number(conn, user_id, pass_number):
    conn.execute('''
        UPDATE student_profiles SET pass_number = %s WHERE user_id = %s
    ''', (pass_number or None, user_id))


def update_teacher_pass_number(conn, user_id, pass_number):
    conn.execute('''
        UPDATE teacher_profiles SET pass_number = %s WHERE user_id = %s
    ''', (pass_number or None, user_id))


def delete_user(conn, user_id):
    conn.execute('DELETE FROM users WHERE id = %s', (user_id,))


def get_student_profile(conn, user_id):
    return conn.execute('''
        SELECT u.*, r.code AS role_code, sp.*, g.name AS group_name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        LEFT JOIN groups g ON g.id = sp.group_id
        WHERE u.id = %s
    ''', (user_id,)).fetchone()


def email_exists(conn, email, exclude_user_id=None):
    if exclude_user_id:
        row = conn.execute(
            'SELECT id FROM users WHERE email = %s AND id != %s',
            (email, exclude_user_id),
        ).fetchone()
    else:
        row = conn.execute('SELECT id FROM users WHERE email = %s', (email,)).fetchone()
    return row is not None
