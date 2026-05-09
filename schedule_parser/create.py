import sqlite3
import os

from schedule_schema import apply_schedule_schema

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "schedule.db")

conn = sqlite3.connect(DB_PATH)
apply_schedule_schema(conn)
conn.close()

print("schedule.db успешно создан.")
