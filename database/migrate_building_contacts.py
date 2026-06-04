#!/usr/bin/env python3
"""Add contact fields to buildings table."""
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


def main():
    with get_connection() as conn:
        conn.execute('''
            ALTER TABLE buildings
            ADD COLUMN IF NOT EXISTS contact_person VARCHAR(255),
            ADD COLUMN IF NOT EXISTS contact_role VARCHAR(128),
            ADD COLUMN IF NOT EXISTS extra_info TEXT
        ''')
        conn.commit()
    print('buildings.contact_* columns ready.')


if __name__ == '__main__':
    main()
