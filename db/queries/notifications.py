def create_notification(conn, user_id, kind, title, body, link_url=None):
    cur = conn.execute('''
        INSERT INTO notifications (user_id, kind, title, body, link_url)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    ''', (user_id, kind, title, body, link_url))
    return cur.fetchone()['id']


def list_notifications(conn, user_id, limit=30, unread_only=False):
    sql = '''
        SELECT id, kind, title, body, link_url, is_read, created_at
        FROM notifications
        WHERE user_id = %s
    '''
    params = [user_id]
    if unread_only:
        sql += ' AND is_read = FALSE'
    sql += ' ORDER BY created_at DESC LIMIT %s'
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def count_unread_notifications(conn, user_id):
    row = conn.execute(
        'SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = FALSE',
        (user_id,),
    ).fetchone()
    return row['c'] if row else 0


def mark_notification_read(conn, notification_id, user_id):
    cur = conn.execute('''
        UPDATE notifications SET is_read = TRUE
        WHERE id = %s AND user_id = %s
        RETURNING id
    ''', (notification_id, user_id))
    return cur.fetchone() is not None


def mark_all_notifications_read(conn, user_id):
    conn.execute(
        'UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE',
        (user_id,),
    )


def upsert_push_subscription(conn, user_id, endpoint, p256dh, auth):
    conn.execute('''
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, endpoint) DO UPDATE SET
            p256dh = EXCLUDED.p256dh,
            auth = EXCLUDED.auth
    ''', (user_id, endpoint, p256dh, auth))


def delete_push_subscription(conn, user_id, endpoint):
    conn.execute(
        'DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s',
        (user_id, endpoint),
    )


def list_push_subscriptions(conn, user_id):
    return conn.execute(
        'SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = %s',
        (user_id,),
    ).fetchall()
