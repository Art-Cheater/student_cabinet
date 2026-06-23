"""Add pass_number to student_profiles."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db.connection import get_db

SQL = '''
ALTER TABLE student_profiles
    ADD COLUMN IF NOT EXISTS pass_number VARCHAR(64);
'''

if __name__ == '__main__':
    with get_db() as conn:
        conn.execute(SQL)
    print('student_profiles.pass_number ready.')
