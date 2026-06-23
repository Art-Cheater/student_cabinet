#!/usr/bin/env python3
"""Применить все миграции схемы (после init_db.py на существующей БД)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = [
    'migrate_app_settings.py',
    'migrate_guard_qr.py',
    'migrate_slot_queue.py',
    'migrate_teacher_notes.py',
    'migrate_student_pass_number.py',
    'migrate_calendar_meta.py',
    'migrate_note_files.py',
    'migrate_teacher_external.py',
    'migrate_building_contacts.py',
    'migrate_notifications.py',
]


def main():
    os.chdir(os.path.join(ROOT, 'database'))
    for name in MIGRATIONS:
        path = os.path.join(ROOT, 'database', name)
        if not os.path.isfile(path):
            continue
        print(f'>> {name}')
        subprocess.check_call([sys.executable, path], cwd=ROOT)
    print('All migrations applied.')


if __name__ == '__main__':
    main()
