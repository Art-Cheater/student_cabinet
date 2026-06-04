#!/usr/bin/env python3
"""Геокод общежитий (Nominatim) → campus_coords.json."""
import json
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
from db.queries.buildings import list_buildings
from parsers.vyatsu_campus import geocode_nominatim


def main():
    path = os.path.join(ROOT, 'data', 'campus_coords.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    dorms = data.setdefault('dorm', {})

    with get_connection() as conn:
        rows = list_buildings(conn, 'dorm')

    for row in rows:
        num = str(row['number'])
        if dorms.get(num):
            continue
        q = f"Киров, {row['address']}"
        lat, lon = geocode_nominatim(q)
        if lat is None:
            print(f'  №{num}: не найден')
            continue
        dorms[num] = [lat, lon]
        print(f'  №{num}: {lat}, {lon}')

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('Сохранено.')


if __name__ == '__main__':
    main()
