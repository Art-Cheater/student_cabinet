import os


def get_note(conn, user_id, event_key):
    return conn.execute('''
        SELECT note_text, updated_at FROM calendar_notes
        WHERE user_id = %s AND event_key = %s
    ''', (user_id, event_key)).fetchone()


def upsert_note(conn, user_id, event_key, event_type, note_text):
    conn.execute('''
        INSERT INTO calendar_notes (user_id, event_key, event_type, note_text, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, event_key) DO UPDATE SET
            note_text = EXCLUDED.note_text,
            event_type = EXCLUDED.event_type,
            updated_at = NOW()
    ''', (user_id, event_key, event_type, note_text or ''))


def load_user_notes_map(conn, user_id, event_keys):
    if not event_keys:
        return {}
    keys = list({k for k in event_keys if k})
    rows = conn.execute('''
        SELECT event_key, note_text FROM calendar_notes
        WHERE user_id = %s AND event_key = ANY(%s)
    ''', (user_id, keys)).fetchall()
    return {r['event_key']: (r['note_text'] or '').strip() for r in rows}


def resolve_slot_id_from_event_key(conn, event_key):
    if not event_key:
        return None
    if event_key.startswith('slot:'):
        try:
            return int(event_key.split(':', 1)[1])
        except ValueError:
            return None
    if event_key.startswith('booking:'):
        try:
            booking_id = int(event_key.split(':', 1)[1])
        except ValueError:
            return None
        row = conn.execute(
            'SELECT slot_id FROM office_bookings WHERE id = %s', (booking_id,),
        ).fetchone()
        return row['slot_id'] if row else None
    return None


def attachment_event_keys_for_lookup(event_key, slot_id=None):
    keys = []
    if event_key:
        keys.append(event_key)
    if slot_id:
        sk = f'slot:{slot_id}'
        if sk not in keys:
            keys.append(sk)
    return keys


def list_attachments_for_event_keys(conn, event_keys):
    if not event_keys:
        return []
    return conn.execute('''
        SELECT id, teacher_user_id, event_key, original_name, uploaded_at
        FROM calendar_attachments WHERE event_key = ANY(%s)
        ORDER BY uploaded_at DESC
    ''', (list(event_keys),)).fetchall()


def list_attachments_for_event(conn, event_key):
    return list_attachments_for_event_keys(conn, [event_key])


def get_attachment(conn, attachment_id):
    return conn.execute(
        'SELECT * FROM calendar_attachments WHERE id = %s', (attachment_id,),
    ).fetchone()


def user_can_download_attachment(conn, user_id, role, attachment_row):
    if not attachment_row:
        return False
    if role == 'admin':
        return True
    if attachment_row['teacher_user_id'] == user_id:
        return True
    event_key = attachment_row.get('event_key') or ''
    if role == 'student' and event_key.startswith('lesson:'):
        parts = event_key.split(':')
        if len(parts) >= 2:
            try:
                lesson_id = int(parts[1])
            except ValueError:
                lesson_id = None
            if lesson_id:
                from db.queries.users import get_student_profile
                prof = get_student_profile(conn, user_id)
                if prof and prof.get('group_id'):
                    row = conn.execute(
                        'SELECT 1 FROM lessons WHERE id = %s AND group_id = %s',
                        (lesson_id, prof['group_id']),
                    ).fetchone()
                    if row:
                        return True
    slot_id = resolve_slot_id_from_event_key(conn, event_key)
    if not slot_id and (attachment_row.get('event_key') or '').startswith('slot:'):
        try:
            slot_id = int(attachment_row['event_key'].split(':', 1)[1])
        except ValueError:
            slot_id = None
    if role == 'student' and slot_id:
        row = conn.execute('''
            SELECT 1 FROM office_bookings
            WHERE slot_id = %s AND student_user_id = %s
              AND status IN ('pending', 'confirmed')
        ''', (slot_id, user_id)).fetchone()
        return row is not None
    return False


def teacher_can_attach_to_event(conn, teacher_user_id, event_key, event_type, slot_id=None):
    event_key = (event_key or '').strip()
    event_type = (event_type or '').strip()
    if event_type == 'office_slot' or event_key.startswith('slot:'):
        sid = slot_id
        if not sid:
            try:
                sid = int(event_key.split(':', 1)[1])
            except (ValueError, IndexError):
                return False
        row = conn.execute(
            'SELECT teacher_user_id FROM office_slots WHERE id = %s', (sid,),
        ).fetchone()
        return row and row['teacher_user_id'] == teacher_user_id
    if event_type == 'lesson' or event_key.startswith('lesson:'):
        parts = event_key.split(':')
        if len(parts) < 2:
            return False
        try:
            lesson_id = int(parts[1])
        except ValueError:
            return False
        from db.queries.users import get_teacher_profile
        prof = get_teacher_profile(conn, teacher_user_id)
        if not prof or not prof.get('schedule_teacher_id'):
            return False
        lesson = conn.execute(
            'SELECT schedule_teacher_id FROM lessons WHERE id = %s', (lesson_id,),
        ).fetchone()
        return lesson and lesson['schedule_teacher_id'] == prof['schedule_teacher_id']
    return False


def insert_attachment(conn, teacher_user_id, event_key, event_type, stored_path, original_name):
    cur = conn.execute('''
        INSERT INTO calendar_attachments
        (teacher_user_id, event_key, event_type, stored_path, original_name)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    ''', (teacher_user_id, event_key, event_type, stored_path, original_name))
    return cur.fetchone()['id']


def delete_attachment(conn, attachment_id, teacher_user_id):
    row = conn.execute('''
        DELETE FROM calendar_attachments
        WHERE id = %s AND teacher_user_id = %s
        RETURNING stored_path
    ''', (attachment_id, teacher_user_id)).fetchone()
    if row and row['stored_path']:
        path = row['stored_path']
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return row is not None


# --- Personal note files (per user, per event) ---

NOTE_FILES_DIR_NAME = 'calendar_note_files'


def list_note_files_for_event(conn, user_id, event_key):
    return conn.execute('''
        SELECT id, original_name, uploaded_at
        FROM calendar_note_files
        WHERE user_id = %s AND event_key = %s
        ORDER BY uploaded_at DESC
    ''', (user_id, event_key)).fetchall()


def get_note_file(conn, file_id):
    return conn.execute(
        'SELECT * FROM calendar_note_files WHERE id = %s', (file_id,),
    ).fetchone()


def delete_note(conn, user_id, event_key):
    conn.execute('''
        DELETE FROM calendar_notes
        WHERE user_id = %s AND event_key = %s
    ''', (user_id, event_key))


def delete_note_file(conn, user_id, file_id):
    row = conn.execute('''
        DELETE FROM calendar_note_files
        WHERE id = %s AND user_id = %s
        RETURNING stored_path
    ''', (file_id, user_id)).fetchone()
    if row and row['stored_path']:
        path = row['stored_path']
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return row is not None


def insert_note_file(conn, user_id, event_key, event_type, stored_path, original_name):
    cur = conn.execute('''
        INSERT INTO calendar_note_files
        (user_id, event_key, event_type, stored_path, original_name)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    ''', (user_id, event_key, event_type, stored_path, original_name))
    return cur.fetchone()['id']
