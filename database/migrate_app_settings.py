#!/usr/bin/env python3
"""Create content.app_settings for admin-managed keys (e.g. VK token)."""
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
from db.connection import DATABASE_URL


def main():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS content')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS content.app_settings (
                key VARCHAR(64) PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
    print('content.app_settings ready.')


if __name__ == '__main__':
    main()
