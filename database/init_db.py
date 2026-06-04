#!/usr/bin/env python3
"""Create StudentCabinet database and apply schema + seed. Not used by Flask app."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:1234@localhost:5432/StudentCabinet',
)
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@vyatsu.ru')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')


def get_admin_url():
    """Connect to postgres DB to create StudentCabinet if missing."""
    if '/StudentCabinet' in DATABASE_URL:
        return DATABASE_URL.rsplit('/', 1)[0] + '/postgres'
    return DATABASE_URL


def ensure_database():
    admin_url = get_admin_url()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                ('StudentCabinet',),
            )
            if not cur.fetchone():
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('StudentCabinet')))
                print('Created database StudentCabinet')


def apply_sql_file(conn, path):
    with open(path, encoding='utf-8') as f:
        conn.execute(f.read())


def seed_admin(conn):
    import bcrypt
    from db.queries.users import get_user_by_email, create_admin_user

    if get_user_by_email(conn, ADMIN_EMAIL):
        print(f'Admin {ADMIN_EMAIL} already exists')
        return
    pwd_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    create_admin_user(conn, ADMIN_EMAIL, pwd_hash, 'Админ', 'Системный', None)
    conn.commit()
    print(f'Created admin: {ADMIN_EMAIL} / (password from ADMIN_PASSWORD env)')


def main():
    ensure_database()
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    seed_path = os.path.join(os.path.dirname(__file__), 'seed.sql')

    with psycopg.connect(DATABASE_URL) as conn:
        apply_sql_file(conn, schema_path)
        conn.commit()
        apply_sql_file(conn, seed_path)
        conn.commit()
        print('Schema and seed applied.')

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        seed_admin(conn)

    print('Done.')


if __name__ == '__main__':
    main()
