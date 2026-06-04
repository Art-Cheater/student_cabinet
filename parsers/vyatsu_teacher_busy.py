"""Parse teacher busy schedule from vyatsu.ru (college + university)."""
import os
import re
import sys
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import requests
from bs4 import BeautifulSoup

TEACHER_INDEX_URL = (
    'https://www.vyatsu.ru/studentu-1/spravochnaya-informatsiya/teacher.html'
)
BASE_URL = 'https://www.vyatsu.ru'
CACHE_TTL_HOURS = 12

DAY_MAP = {
    0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг',
    4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье',
}


def _headers():
    return {
        'User-Agent': 'Mozilla/5.0 (compatible; StudentCabinet/1.0)',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }


def _normalize_name(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def _teacher_match_score(link_text, last_name, first_name, middle_name):
    t = _normalize_name(link_text)
    ln = _normalize_name(last_name)
    fn = _normalize_name(first_name)
    if not ln or ln not in t:
        return 0
    score = 10
    if fn and fn[:1] in t:
        score += 5
        if fn in t:
            score += 3
    if middle_name:
        mn = _normalize_name(middle_name)
        if mn and mn[:1] in t:
            score += 2
    return score


def find_teacher_link(html, last_name, first_name, middle_name=None):
    soup = BeautifulSoup(html, 'html.parser')
    best = None
    best_score = 0
    for a in soup.find_all('a', href=True):
        text = a.get_text(' ', strip=True)
        if len(text) < 5 or len(text) > 120:
            continue
        score = _teacher_match_score(text, last_name, first_name, middle_name)
        if score > best_score:
            best_score = score
            href = a['href']
            if not href.startswith('http'):
                href = urljoin(BASE_URL, href)
            best = (href, text)
    if best_score < 10:
        return None, None, 'not_found'
    return best[0], best[1], 'matched'


def _parse_week_range(text):
    m = re.search(
        r'c\s*(\d{1,2})\s*(\d{1,2})\s*(\d{4})\s*по\s*(\d{1,2})\s*(\d{1,2})\s*(\d{4})',
        text, re.I,
    )
    if not m:
        return None, None
    try:
        start = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        end = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        return start, end
    except ValueError:
        return None, None


def _parse_time_range(cell_text):
    m = re.search(
        r'(\d{1,2})[.:](\d{2})\s*[-–]\s*(\d{1,2})[.:](\d{2})',
        cell_text,
    )
    if not m:
        return None, None
    return f'{int(m.group(1)):02d}:{m.group(2)}', f'{int(m.group(3)):02d}:{m.group(4)}'


def _events_from_schedule_html(html, week_start, week_end):
    soup = BeautifulSoup(html, 'html.parser')
    events = []
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        header_cells = [c.get_text(' ', strip=True) for c in rows[0].find_all(['th', 'td'])]
        day_cols = []
        for i, h in enumerate(header_cells):
            for wd, idx in DAY_MAP.items():
                if wd.lower() in h.lower()[:12]:
                    day_cols.append((i, idx))
                    break
        if not day_cols:
            continue
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            time_text = cells[0].get_text(' ', strip=True)
            t_start, t_end = _parse_time_range(time_text)
            if not t_start:
                continue
            for col_idx, weekday in day_cols:
                if col_idx >= len(cells):
                    continue
                cell = cells[col_idx].get_text(' ', strip=True)
                if not cell or len(cell) < 2:
                    continue
                if cell.lower() in ('', '-', '—', 'x', 'х'):
                    continue
                d = week_start
                while d <= week_end:
                    if d.weekday() == weekday:
                        title = cell[:200]
                        events.append({
                            'id': f'uni-{d.isoformat()}-{t_start}-{title[:20]}',
                            'title': title,
                            'start': f'{d.isoformat()}T{t_start}:00',
                            'end': f'{d.isoformat()}T{t_end}:00',
                            'type': 'university_lesson',
                            'source': 'vyatsu',
                        })
                        break
                    d += timedelta(days=1)
    return events


def _current_week_bounds():
    today = date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


def fetch_teacher_university_events(last_name, first_name, middle_name=None):
    """Return (events, matched_name, link_status)."""
    try:
        resp = requests.get(TEACHER_INDEX_URL, timeout=35, headers=_headers())
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'
        index_html = resp.text
    except Exception as exc:
        return [], None, f'fetch_error:{exc}'

    link, matched_name, status = find_teacher_link(
        index_html, last_name, first_name, middle_name,
    )
    if not link:
        return [], None, status

    try:
        resp2 = requests.get(link, timeout=35, headers=_headers())
        resp2.raise_for_status()
        resp2.encoding = resp2.apparent_encoding or 'utf-8'
        sched_html = resp2.text
    except Exception as exc:
        return [], matched_name, f'schedule_error:{exc}'

    week_start, week_end = _current_week_bounds()
    ranges = re.findall(
        r'c\s*\d{1,2}\s*\d{1,2}\s*\d{4}\s*по\s*\d{1,2}\s*\d{1,2}\s*\d{4}',
        sched_html, re.I,
    )
    if ranges:
        ws, we = _parse_week_range(ranges[0])
        if ws and we:
            week_start, week_end = ws, we

    events = _events_from_schedule_html(sched_html, week_start, week_end)
    if not events:
        events = _events_from_schedule_html(index_html, week_start, week_end)
    return events, matched_name, 'ok' if events else 'empty_schedule'


def get_teacher_university_events(conn, teacher_user_id, last_name, first_name,
                                 middle_name=None, force_refresh=False):
    from db.queries.external_schedule import (
        get_external_schedule_cache, save_external_schedule_cache,
    )

    if not force_refresh:
        cached, meta = get_external_schedule_cache(conn, teacher_user_id)
        if cached is not None:
            info = None
            if meta:
                info = {
                    'matched_name': meta.get('matched_name'),
                    'link_status': meta.get('link_status'),
                }
            return cached, info

    events, matched_name, status = fetch_teacher_university_events(
        last_name, first_name, middle_name,
    )
    save_external_schedule_cache(
        conn, teacher_user_id, events, matched_name, status,
    )
    return events, {'matched_name': matched_name, 'link_status': status}
