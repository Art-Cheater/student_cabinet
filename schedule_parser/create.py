#!/usr/bin/env python3
"""Deprecated: use python database/init_db.py for PostgreSQL setup."""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print('Используйте: python database/init_db.py')
sys.path.insert(0, ROOT)
