"""CRUD for campus places (buildings + dorms) in table buildings.

kind: 'building' | 'dorm'. Schema is 3NF; see database/schema.sql and
SYSTEM_OVERVIEW.txt section «Карта кампуса (buildings)».
"""


def list_buildings(conn, kind=None):
    if kind:
        return conn.execute(
            'SELECT * FROM buildings WHERE kind = %s ORDER BY number',
            (kind,),
        ).fetchall()
    return conn.execute('SELECT * FROM buildings ORDER BY kind, number').fetchall()


def get_building_by_number(conn, number, kind='building'):
    return conn.execute(
        'SELECT * FROM buildings WHERE number = %s AND kind = %s',
        (int(number), kind),
    ).fetchone()


def upsert_building(
    conn,
    number,
    name,
    address,
    phone,
    image_url,
    lat,
    lon,
    kind='building',
    contact_person=None,
    contact_role=None,
    extra_info=None,
):
    conn.execute('''
        INSERT INTO buildings (
            number, name, address, phone, image_url, lat, lon, kind,
            contact_person, contact_role, extra_info
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (number, kind) DO UPDATE SET
            name = EXCLUDED.name,
            address = EXCLUDED.address,
            phone = EXCLUDED.phone,
            image_url = EXCLUDED.image_url,
            lat = EXCLUDED.lat,
            lon = EXCLUDED.lon,
            contact_person = EXCLUDED.contact_person,
            contact_role = EXCLUDED.contact_role,
            extra_info = EXCLUDED.extra_info
    ''', (
        number, name, address, phone, image_url, lat, lon, kind,
        contact_person, contact_role, extra_info,
    ))
