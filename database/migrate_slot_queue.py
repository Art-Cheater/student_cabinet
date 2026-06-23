"""Queue on lesson + work submissions for office slots."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connection import get_db


def main():
    with get_db() as conn:
        conn.execute('''
            ALTER TABLE office_slots
            ADD COLUMN IF NOT EXISTS enable_queue BOOLEAN NOT NULL DEFAULT FALSE
        ''')
        conn.execute('''
            ALTER TABLE office_slots
            ADD COLUMN IF NOT EXISTS enable_submission BOOLEAN NOT NULL DEFAULT FALSE
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS office_queue_entries (
                id SERIAL PRIMARY KEY,
                slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
                student_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (slot_id, student_user_id)
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_office_queue_slot
            ON office_queue_entries(slot_id, position)
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS office_submissions (
                id SERIAL PRIMARY KEY,
                slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
                student_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                stored_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_office_submissions_slot
            ON office_submissions(slot_id)
        ''')
    print('migrate_slot_queue: OK')


if __name__ == '__main__':
    main()
