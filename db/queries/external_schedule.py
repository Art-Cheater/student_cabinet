import json
from datetime import datetime, timedelta, timezone


CACHE_TTL_HOURS = 12


def get_external_schedule_cache(conn, teacher_user_id, source='vyatsu'):
    row = conn.execute('''
        SELECT payload, matched_name, link_status, fetched_at
        FROM teacher_external_schedule
        WHERE teacher_user_id = %s AND source = %s
    ''', (teacher_user_id, source)).fetchone()
    if not row:
        return None, None
    fetched = row['fetched_at']
    if fetched:
        now = datetime.now(timezone.utc)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        if now - fetched > timedelta(hours=CACHE_TTL_HOURS):
            return None, row
    payload = row['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload or [], row


def save_external_schedule_cache(conn, teacher_user_id, events, matched_name,
                               link_status, source='vyatsu'):
    conn.execute('''
        INSERT INTO teacher_external_schedule
        (teacher_user_id, source, matched_name, link_status, payload, fetched_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
        ON CONFLICT (teacher_user_id) DO UPDATE SET
            matched_name = EXCLUDED.matched_name,
            link_status = EXCLUDED.link_status,
            payload = EXCLUDED.payload,
            fetched_at = NOW()
    ''', (
        teacher_user_id, source, matched_name, link_status,
        json.dumps(events, ensure_ascii=False),
    ))


def list_vyatsu_link_statuses(conn):
    return conn.execute('''
        SELECT teacher_user_id, matched_name, link_status, fetched_at
        FROM teacher_external_schedule WHERE source = 'vyatsu'
    ''').fetchall()
