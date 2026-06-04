def get_setting(conn, key, default=''):
    row = conn.execute(
        'SELECT value FROM content.app_settings WHERE key = %s',
        (key,),
    ).fetchone()
    if row and row.get('value'):
        return row['value']
    return default


def set_setting(conn, key, value):
    conn.execute('''
        INSERT INTO content.app_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW()
    ''', (key, value or ''))


def mask_token(token):
    t = (token or '').strip()
    if len(t) <= 8:
        return '••••' if t else ''
    return t[:6] + '••••' + t[-4:]
