#!/usr/bin/env python3
"""Guard role, teacher pass fields, QR tokens, cancelled booking status."""
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
        conn.execute('''
            INSERT INTO roles (code, title) VALUES ('guard', 'Охранник')
            ON CONFLICT (code) DO NOTHING
        ''')
        conn.execute('''
            ALTER TABLE teacher_profiles
            ADD COLUMN IF NOT EXISTS pass_number VARCHAR(64),
            ADD COLUMN IF NOT EXISTS department VARCHAR(255)
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS qr_access_tokens (
                id SERIAL PRIMARY KEY,
                token UUID NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_type VARCHAR(16) NOT NULL
                    CHECK (subject_type IN ('student', 'teacher')),
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMPTZ
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_qr_tokens_token ON qr_access_tokens(token)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_qr_tokens_user ON qr_access_tokens(user_id)
        ''')
        conn.execute('''
            ALTER TABLE office_bookings DROP CONSTRAINT IF EXISTS office_bookings_status_check
        ''')
        conn.execute('''
            ALTER TABLE office_bookings ADD CONSTRAINT office_bookings_status_check
            CHECK (status IN ('pending', 'confirmed', 'rejected', 'cancelled'))
        ''')
    print('Guard/QR migration done.')


if __name__ == '__main__':
    main()
