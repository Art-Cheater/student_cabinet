#!/usr/bin/env python3
"""Parse buildings and dorms from vyatsu.ru and upsert into PostgreSQL."""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import requests
from bs4 import BeautifulSoup

from db.connection import get_connection
from db.queries.buildings import upsert_building
from parsers.vyatsu_buildings import (
    BUILDINGS_URL,
    parse_building_institute_notes,
    parse_buildings_page,
)

from parsers.vyatsu_dorms import DORMS_URL, parse_dorms_page
def load_campus_coords_json():
    path = os.path.join(ROOT, 'data', 'campus_coords.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    out = {}
    for kind in ('building', 'dorm'):
        for num, pair in (data.get(kind) or {}).items():
            out[(kind, int(num))] = (float(pair[0]), float(pair[1]))
    return out


def load_campus_overrides():
    path = os.path.join(ROOT, 'data', 'campus_overrides.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


JSON_COORDS = load_campus_coords_json()
CAMPUS_OVERRIDES = load_campus_overrides()


def get_override(kind, number):
    block = CAMPUS_OVERRIDES.get(kind) or {}
    return block.get(str(number)) or block.get(number)


def fetch_html(url):
    resp = requests.get(url, timeout=30, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; StudentCabinet/1.0; +https://vyatsu.ru)',
    })
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or 'utf-8'
    return resp.text


def normalize_address(raw):
    addr = re.sub(r'\s+', ' ', (raw or '')).strip()
    addr = re.sub(r',\s*Тел\..*$', '', addr, flags=re.I)
    return addr[:500]


def geocode_nominatim(query):
    """Free geocoder (no API key). Respect 1 req/sec policy."""
    if not query:
        return None, None
    try:
        time.sleep(1.1)
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'ru'},
            headers={'User-Agent': 'StudentCabinet-VyatSU/1.0 (campus map)'},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None, None
        return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        return None, None


def resolve_coords(kind, number, address, lat, lon):
    ov = get_override(kind, number)
    if ov and ov.get('lat') is not None and ov.get('lon') is not None:
        return float(ov['lat']), float(ov['lon'])
    if lat is not None and lon is not None:
        return lat, lon
    key = (kind, number)
    if key in JSON_COORDS:
        return JSON_COORDS[key]
    if os.getenv('CAMPUS_GEOCODE_NOMINATIM', '1').strip() not in ('0', 'false', 'no'):
        q = (ov.get('geocode_query') if ov else None) or f'Киров, {address}'
        return geocode_nominatim(q) if address else (None, None)
    return None, None


def sync_buildings(conn, html=None):
    """Загрузить корпуса с vyatsu.ru в БД."""
    global JSON_COORDS
    JSON_COORDS = load_campus_coords_json()
    html = html or fetch_html(BUILDINGS_URL)
    buildings = parse_buildings_page(html)
    institute_notes = parse_building_institute_notes(html)
    for e in buildings:
        upsert_entry(conn, e, extra_info=institute_notes.get(e['number']))
    return buildings, institute_notes


def sync_dorms(conn, html=None):
    global JSON_COORDS
    JSON_COORDS = load_campus_coords_json()
    html = html or fetch_html(DORMS_URL)
    dorms = parse_dorms_page(html)
    for e in dorms:
        upsert_entry(conn, e)
    return dorms


def upsert_entry(conn, entry, extra_info=None):
    kind = entry['kind']
    num = entry['number']
    ov = get_override(kind, num)
    if ov and ov.get('address'):
        entry['address'] = ov['address']
    lat, lon = resolve_coords(kind, num, entry.get('address'), None, None)
    upsert_building(
        conn,
        num,
        entry['name'],
        entry.get('address') or '',
        entry.get('phone') or '',
        entry.get('image_url') or '',
        lat,
        lon,
        kind,
        contact_person=entry.get('contact_person'),
        contact_role=entry.get('contact_role'),
        extra_info=extra_info or entry.get('extra_info'),
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sync campus data from vyatsu.ru')
    parser.add_argument('--buildings-only', action='store_true', help='Только учебные корпуса')
    parser.add_argument('--dorms-only', action='store_true', help='Только общежития')
    args = parser.parse_args()

    conn = get_connection()
    try:
        if not args.dorms_only:
            buildings, notes = sync_buildings(conn)
            with_coords = sum(1 for b in buildings if resolve_coords(
                'building', b['number'], b.get('address'), None, None
            )[0] is not None)
            print(f'Корпуса: {len(buildings)} (с координатами: {with_coords})')
            for e in buildings:
                n = notes.get(e['number'])
                if n:
                    print(f"  №{e['number']}: {e['address'][:55]}… | деканат/дирекция: да")

        if not args.buildings_only:
            dorms = sync_dorms(conn)
            with_coords = sum(1 for d in dorms if resolve_coords(
                'dorm', d['number'], d.get('address'), None, None
            )[0] is not None)
            print(f'Общежития: {len(dorms)} (с координатами: {with_coords})')
            for e in dorms:
                print(f"  №{e['number']}: {e['contact_person']} — {e['phone']}")

        conn.commit()
        print('Готово.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
