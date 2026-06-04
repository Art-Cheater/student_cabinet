import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:1234@localhost:5432/StudentCabinet',
)


@contextmanager
def get_db():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection():
    """Raw connection for scripts; caller commits/closes."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)
