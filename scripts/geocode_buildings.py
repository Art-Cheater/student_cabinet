#!/usr/bin/env python3
"""Один раз: геокод корпусов без Яндекс API (Nominatim) → campus_coords.json."""
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
from parsers.vyatsu_campus import geocode_nominatim, get_override, resolve_coords


def main():
    path = os.path.join(ROOT, 'data', 'campus_coords.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    buildings = data.setdefault('building', {})

    with get_connection() as conn:
        rows = list_buildings(conn, 'building')

    updated = 0
    for row in rows:
        num = str(row['number'])
        if num in buildings and buildings[num]:
            continue
        ov = get_override('building', row['number'])
        q = (ov.get('geocode_query') if ov else None) or f"Киров, {row['address']}"
        if not q or len(q) < 12:
            continue
        lat, lon = geocode_nominatim(q)
        if lat is None:
            print(f'  №{num}: не найден — {q[:60]}')
            continue
        buildings[num] = [lat, lon]
        updated += 1
        print(f'  №{num}: {lat}, {lon}')

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Сохранено в campus_coords.json: {updated} новых точек')


if __name__ == '__main__':
    main()
