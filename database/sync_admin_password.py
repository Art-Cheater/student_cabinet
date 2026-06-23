#!/usr/bin/env python3
"""Синхронизировать пароль admin@… из ADMIN_PASSWORD в .env (если пользователь уже есть)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import bcrypt

from db.connection import get_db
from db.queries.users import get_user_by_email

ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@vyatsu.ru').strip().lower()
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')


def main():
    if not ADMIN_PASSWORD:
        print('ADMIN_PASSWORD is empty')
        sys.exit(1)
    pwd_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    with get_db() as conn:
        user = get_user_by_email(conn, ADMIN_EMAIL)
        if not user:
            print(f'Admin {ADMIN_EMAIL} not found — run: python database/init_db.py')
            sys.exit(1)
        if user['role_code'] != 'admin':
            print(f'{ADMIN_EMAIL} is not admin (role={user["role_code"]})')
            sys.exit(1)
        conn.execute(
            'UPDATE users SET password_hash = %s WHERE id = %s',
            (pwd_hash, user['id']),
        )
    print(f'Password updated for {ADMIN_EMAIL} (from ADMIN_PASSWORD in .env)')


if __name__ == '__main__':
    main()
