"""In-app notifications, push subscriptions, queue passed flag."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connection import get_db


def main():
    with get_db() as conn:
        conn.execute('''
            ALTER TABLE office_queue_entries
            ADD COLUMN IF NOT EXISTS passed_at TIMESTAMPTZ
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind VARCHAR(32) NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                link_url TEXT,
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON notifications(user_id, is_read, created_at DESC)
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, endpoint)
            )
        ''')
    print('migrate_notifications: OK')


if __name__ == '__main__':
    main()
