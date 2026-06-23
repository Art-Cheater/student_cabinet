import uuid
from datetime import datetime, timedelta, timezone


def revoke_active_tokens(conn, user_id):
    conn.execute('''
        UPDATE qr_access_tokens
        SET revoked_at = NOW()
        WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()
    ''', (user_id,))


def issue_token(conn, user_id, subject_type, ttl_seconds=60):
    revoke_active_tokens(conn, user_id)
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    conn.execute('''
        INSERT INTO qr_access_tokens (token, user_id, subject_type, expires_at)
        VALUES (%s, %s, %s, %s)
    ''', (token, user_id, subject_type, expires))
    return token, expires


def get_valid_token(conn, token_str):
    return conn.execute('''
        SELECT q.*, u.last_name, u.first_name, u.middle_name, u.is_active,
               u.email
        FROM qr_access_tokens q
        JOIN users u ON u.id = q.user_id
        WHERE q.token = %s::uuid
          AND q.revoked_at IS NULL
          AND q.expires_at > NOW()
    ''', (token_str,)).fetchone()
