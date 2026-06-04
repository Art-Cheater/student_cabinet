#!/usr/bin/env python3
"""Add calendar_note_files table for personal event attachments."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

from db.connection import get_connection

SQL = '''
CREATE TABLE IF NOT EXISTS calendar_note_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    stored_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_calendar_note_files_user_event
    ON calendar_note_files(user_id, event_key);
'''


def main():
    with get_connection() as conn:
        conn.execute(SQL)
        conn.commit()
    print('calendar_note_files ready.')


if __name__ == '__main__':
    main()
