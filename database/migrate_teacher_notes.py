"""Teacher personal calendar notes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connection import get_db


def main():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS teacher_personal_events (
                id SERIAL PRIMARY KEY,
                teacher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_date DATE NOT NULL,
                time_start TIME NOT NULL,
                time_end TIME NOT NULL,
                title TEXT NOT NULL,
                color VARCHAR(16),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_teacher_personal_date
            ON teacher_personal_events(teacher_user_id, event_date)
        ''')
    print('migrate_teacher_notes: OK')


if __name__ == '__main__':
    main()
