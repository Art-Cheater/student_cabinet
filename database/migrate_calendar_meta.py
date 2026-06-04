#!/usr/bin/env python3
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
CREATE TABLE IF NOT EXISTS calendar_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    note_text TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, event_key)
);

CREATE TABLE IF NOT EXISTS calendar_attachments (
    id SERIAL PRIMARY KEY,
    teacher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    stored_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_attachments_event ON calendar_attachments(event_key);
'''


def main():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(SQL)
        conn.commit()
    print('calendar_notes / calendar_attachments ready.')


if __name__ == '__main__':
    main()
