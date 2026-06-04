#!/usr/bin/env python3
"""One-time migration from SQLite files to PostgreSQL."""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import bcrypt
from db.connection import get_connection
from db.queries.groups import get_or_create_group
from db.queries.schedule import (
    get_or_create_schedule_teacher, get_or_create_classroom,
    insert_upload, insert_lesson,
)
from db.queries.users import get_role_id, get_user_by_email
from db.queries.buildings import upsert_building
from db.queries.content import save_news_cache

STUDENTS_DB = os.path.join(ROOT, 'students.db')
SCHEDULE_DB = os.path.join(ROOT, 'schedule.db')
CONTENT_DB = os.path.join(ROOT, 'content.db')

# Seed coordinates from legacy app.py
BUILDINGS_SEED = [
    (1, 'Корпус №1', 'ул. Московская, д. 36', '(8332) 70-82-67',
     'https://www.vyatsu.ru/uploads/image/2411/img_9401.jpg', 58.6032080, 49.6454819, 'building'),
    (2, 'Корпус №2', 'ул. Московская, д. 39', '(8332) 70-82-27',
     'https://www.vyatsu.ru/uploads/image/2411/img_9369.jpg', 58.6032080, 49.6454819, 'building'),
    (3, 'Корпус №3', 'ул. Московская, д. 29', '(8332) 64-56-27',
     'https://www.vyatsu.ru/uploads/image/1308/3_korp_m.jpg', 58.6029204, 49.6319040, 'building'),
    (5, 'Корпус №5 (Колледж)', 'ул. Владимирская, д. 55', '(8332) 64-26-24',
     'https://www.vyatsu.ru/uploads/image/1708/img_5209.jpg', 58.6133600, 49.6662800, 'building'),
]
DORMS_SEED = [
    (1, 'Общежитие №1', 'Октябрьский пр-кт, д. 113', '(8332) 64-45-21',
     'https://www.vyatsu.ru/uploads/image/1710/7obschezhitie1_(2).jpg', 58.6032080, 49.6454819, 'dorm'),
]


def migrate_buildings(conn):
    for row in BUILDINGS_SEED + DORMS_SEED:
        upsert_building(conn, *row)


def migrate_students(conn):
    if not os.path.exists(STUDENTS_DB):
        print('No students.db, skip')
        return
    sconn = sqlite3.connect(STUDENTS_DB)
    sconn.row_factory = sqlite3.Row
    role_id = get_role_id(conn, 'student')
    for u in sconn.execute('SELECT * FROM users').fetchall():
        if get_user_by_email(conn, u['email']):
            continue
        group_id = None
        if u['group_name']:
            group_id = get_or_create_group(conn, u['group_name'])
        cur = conn.execute('''
            INSERT INTO users (email, password_hash, role_id, last_name, first_name, middle_name)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (
            u['email'], u['password_hash'], role_id,
            u['last_name'], u['first_name'], u['middle_name'],
        ))
        uid = cur.fetchone()['id']
        card = sconn.execute(
            'SELECT * FROM student_cards WHERE user_id = ?', (u['id'],)
        ).fetchone()
        if card:
            conn.execute('''
                INSERT INTO student_profiles
                (user_id, group_id, student_id, course, card_number_hash, card_number_last4,
                 face_photo_path, study_form, issue_date, course_number, verification_signature)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (
                uid, group_id, u['student_id'], u['course'],
                card['card_number_hash'], card['card_number_last4'],
                card['face_photo_path'], card['study_form'], card['issue_date'],
                card['course_number'], card['verification_signature'],
            ))
    sconn.close()
    print('Students migrated')


def migrate_schedule(conn):
    if not os.path.exists(SCHEDULE_DB):
        print('No schedule.db, skip')
        return
    sconn = sqlite3.connect(SCHEDULE_DB)
    sconn.row_factory = sqlite3.Row
    conn.execute('DELETE FROM lessons')
    conn.execute('DELETE FROM uploads')
    for up in sconn.execute('SELECT * FROM uploads ORDER BY id').fetchall():
        upload_id = insert_upload(conn, up['filename'])
        lessons = sconn.execute(
            'SELECT * FROM lessons WHERE upload_id = ?', (up['id'],)
        ).fetchall()
        for l in lessons:
            g = sconn.execute('SELECT name FROM groups WHERE id = ?', (l['group_id'],)).fetchone()
            t = sconn.execute(
                'SELECT name FROM teachers WHERE id = ?', (l['teacher_id'],)
            ).fetchone() if l['teacher_id'] else None
            c = sconn.execute(
                'SELECT name FROM classrooms WHERE id = ?', (l['classroom_id'],)
            ).fetchone() if l['classroom_id'] else None
            gid = get_or_create_group(conn, g['name'] if g else '')
            tid = get_or_create_schedule_teacher(conn, t['name'] if t else '')
            cid = get_or_create_classroom(conn, c['name'] if c else '')
            insert_lesson(
                conn, upload_id, gid, tid, cid,
                l['day_name'], l['lesson_number'],
                l['time_start'], l['time_end'], l['subject'], l['lesson_type'],
            )
    sconn.close()
    print('Schedule migrated')


def migrate_content(conn):
    if not os.path.exists(CONTENT_DB):
        return
    sconn = sqlite3.connect(CONTENT_DB)
    sconn.row_factory = sqlite3.Row
    for row in sconn.execute('SELECT * FROM vk_news_cache').fetchall():
        conn.execute('''
            INSERT INTO content.vk_news_cache
            (post_id, title, summary, post_date, post_url, image_url)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (post_id) DO NOTHING
        ''', (
            row['post_id'], row['title'], row['summary'],
            row['post_date'], row['post_url'], row['image_url'],
        ))
    sconn.close()
    print('VK cache migrated')


def main():
    conn = get_connection()
    try:
        migrate_buildings(conn)
        migrate_students(conn)
        migrate_schedule(conn)
        migrate_content(conn)
        conn.commit()
    finally:
        conn.close()
    print('Migration complete.')


if __name__ == '__main__':
    main()
