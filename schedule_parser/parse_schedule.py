import sqlite3
import os
import re
import sys
from openpyxl import load_workbook


# =====================================
# Пути
# =====================================
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "..", "schedule.db")


# =====================================
# Excel файл
# =====================================
if len(sys.argv) > 1:
    FILE_NAME = sys.argv[1]
else:
    FILE_NAME = os.path.join(BASE_DIR, "uploads", "schedule.xlsx")


# =====================================
# Проверка файла
# =====================================
if not os.path.exists(FILE_NAME):
    print("Excel файл не найден:", FILE_NAME)
    sys.exit()


# =====================================
# Подключение БД
# =====================================
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


# =====================================
# Очистка старого расписания
# =====================================
cur.execute("DELETE FROM lessons")
cur.execute("DELETE FROM uploads")
conn.commit()


# =====================================
# helpers
# =====================================
ALLOWED_NAME_TABLES = {"groups", "teachers", "classrooms"}


def get_or_create(table, value):
    if not value:
        return None

    value = value.strip()
    if table not in ALLOWED_NAME_TABLES:
        raise ValueError(f"Недопустимое имя таблицы: {table}")

    cur.execute(f"SELECT id FROM {table} WHERE name=?", (value,))
    row = cur.fetchone()

    if row:
        return row[0]

    cur.execute(f"INSERT INTO {table}(name) VALUES(?)", (value,))
    conn.commit()

    return cur.lastrowid


def split_time(text):
    if "-" in text:
        arr = text.split("-")
        return arr[0].strip(), arr[1].strip()

    return "", ""


# =====================================
# Загрузка excel
# =====================================
wb = load_workbook(FILE_NAME, data_only=True)
ws = wb.active


# =====================================
# merged cells
# =====================================
merged = {}

for rng in ws.merged_cells.ranges:
    min_col, min_row, max_col, max_row = rng.bounds
    val = ws.cell(min_row, min_col).value

    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            merged[(r, c)] = val


def get_val(row, col):
    val = ws.cell(row, col).value

    if val is None:
        val = merged.get((row, col))

    if val is None:
        return ""

    return str(val).strip()


# =====================================
# запись загрузки файла
# =====================================
cur.execute(
    "INSERT INTO uploads(filename) VALUES(?)",
    (os.path.basename(FILE_NAME),)
)
conn.commit()

upload_id = cur.lastrowid


# =====================================
# Поиск групп
# =====================================
GROUP_ROW = 19
HEADER_ROW = 20

group_columns = {}

for col in range(1, ws.max_column + 1):

    header = get_val(HEADER_ROW, col)

    if header == "Дисциплина,модуль":

        group_text = get_val(GROUP_ROW, col)

        names = re.findall(
            r'[А-Яа-яA-Za-z0-9\-]+-\d+-\d+-\d+',
            group_text
        )

        for name in names:
            group_columns[name] = col


print("Найдено групп:", len(group_columns))


# =====================================
# Парсинг расписания
# =====================================
for group_name, col in group_columns.items():

    print("Обработка:", group_name)

    group_id = get_or_create("groups", group_name)

    current_day = ""
    lesson_number = 0

    for row in range(21, ws.max_row + 1):

        day = get_val(row, 7)
        time_text = get_val(row, 8)

        if day:
            current_day = day.strip()
            lesson_number = 0

        subject = get_val(row, col)
        lesson_type = get_val(row, col + 1)
        teacher = get_val(row, col + 2)
        room = get_val(row, col + 3)

        if subject:

            lesson_number += 1

            teacher_id = get_or_create("teachers", teacher)
            classroom_id = get_or_create("classrooms", room)

            time_start, time_end = split_time(time_text)

            cur.execute("""
                INSERT INTO lessons (
                    upload_id,
                    group_id,
                    teacher_id,
                    classroom_id,
                    day_name,
                    lesson_number,
                    time_start,
                    time_end,
                    subject,
                    lesson_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                upload_id,
                group_id,
                teacher_id,
                classroom_id,
                current_day,
                lesson_number,
                time_start,
                time_end,
                subject,
                lesson_type
            ))

conn.commit()
conn.close()

print("Расписание успешно загружено в schedule.db")