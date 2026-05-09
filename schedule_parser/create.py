import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "schedule.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.executescript("""

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS classrooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    upload_id INTEGER,
    group_id INTEGER NOT NULL,
    teacher_id INTEGER,
    classroom_id INTEGER,

    day_name TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,

    time_start TEXT,
    time_end TEXT,

    subject TEXT NOT NULL,
    lesson_type TEXT,

    FOREIGN KEY(upload_id) REFERENCES uploads(id),
    FOREIGN KEY(group_id) REFERENCES groups(id),
    FOREIGN KEY(teacher_id) REFERENCES teachers(id),
    FOREIGN KEY(classroom_id) REFERENCES classrooms(id)
);

CREATE INDEX IF NOT EXISTS idx_lessons_group ON lessons(group_id);
CREATE INDEX IF NOT EXISTS idx_lessons_day ON lessons(day_name);
CREATE INDEX IF NOT EXISTS idx_lessons_teacher ON lessons(teacher_id);

""")

conn.commit()
conn.close()

print("schedule.db успешно создан.")