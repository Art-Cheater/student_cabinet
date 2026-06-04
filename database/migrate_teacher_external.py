#!/usr/bin/env python3
"""Add teacher_external_schedule table to existing DB."""
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

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:1234@localhost:5432/StudentCabinet',
)

SQL = '''
CREATE TABLE IF NOT EXISTS teacher_external_schedule (
    teacher_user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    source VARCHAR(32) NOT NULL DEFAULT 'vyatsu',
    matched_name TEXT,
    link_status VARCHAR(64),
    payload JSONB NOT NULL DEFAULT '[]'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
'''


def main():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(SQL)
        conn.commit()
    print('teacher_external_schedule ready.')


if __name__ == '__main__':
    main()
