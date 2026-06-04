def get_or_create_group(conn, name):
    name = (name or '').strip()
    if not name:
        return None
    row = conn.execute('SELECT id FROM groups WHERE name = %s', (name,)).fetchone()
    if row:
        return row['id']
    cur = conn.execute(
        'INSERT INTO groups (name) VALUES (%s) RETURNING id', (name,)
    )
    return cur.fetchone()['id']


def get_group_by_name(conn, name):
    return conn.execute('SELECT * FROM groups WHERE name = %s', (name,)).fetchone()


def list_groups(conn):
    return conn.execute('SELECT id, name FROM groups ORDER BY name').fetchall()


def search_groups(conn, query='', limit=30):
    q = (query or '').strip()
    if q:
        return conn.execute(
            'SELECT id, name FROM groups WHERE name ILIKE %s ORDER BY name LIMIT %s',
            (f'%{q}%', limit),
        ).fetchall()
    return conn.execute('SELECT id, name FROM groups ORDER BY name LIMIT %s', (limit,)).fetchall()


def resolve_group_ids_by_names(conn, names):
    ids = []
    for name in names:
        name = (name or '').strip()
        if not name:
            continue
        row = conn.execute('SELECT id FROM groups WHERE name = %s', (name,)).fetchone()
        if row:
            ids.append(row['id'])
        else:
            ids.append(get_or_create_group(conn, name))
    return ids
