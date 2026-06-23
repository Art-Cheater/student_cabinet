import html as html_lib
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

import requests

from db.connection import get_db
from db.queries.content import (
    NEWS_CACHE_SIZE, get_last_news_fetch, load_news_cache, merge_news_cache,
)

NEWS_CACHE_TTL_SECONDS = int(os.getenv('VK_NEWS_TTL_SECONDS', '3600'))
VK_WALL_MAX_OFFSET = int(os.getenv('VK_WALL_MAX_OFFSET', '150'))
VK_WALL_PAGE_SIZE = 10
_news_refresh_lock = threading.Lock()

VK_GROUP_URL = 'https://vk.com/kollegevyatsu'
VK_GROUP_ID = 85060840
VK_GROUP_DOMAIN = os.getenv('VK_GROUP_DOMAIN', 'kollegevyatsu')

MONTHS_RU = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5,
    'июн': 6, 'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
}

_IMAGE_URL_PATTERNS = (
    r'background-image:\s*url\(["\']?(https?://[^"\')\s]+)',
    r'(?:data-src|src)=["\'](https?://[^"\']+)["\']',
    r'(https://(?:sun\d+-?\d+\.)?userapi\.com/[^"\'\s>]+)',
    r'(https://(?:pp\.)?userapi\.com/[^"\'\s>]+)',
    r'(https://[^"\']*vkuserphoto\.ru/[^"\'\s>]+)',
    r'(https://[^"\']*im\.vk\.com/[^"\'\s>]+)',
    r'(https://[^"\']*mycdn\.me/[^"\'\s>]+)',
    r'(https://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)',
)


def _format_post_date(dt):
    return dt.strftime('%d.%m.%Y %H:%M')


def _date_from_unix(ts):
    try:
        ts = int(ts)
        if ts > 1_000_000_000_000:
            ts //= 1000
        if ts > 0:
            return datetime.fromtimestamp(ts)
    except (TypeError, ValueError, OSError):
        pass
    return None


def _parse_relative_ru(text, now=None):
    now = now or datetime.now()
    t = (text or '').strip().lower()
    if not t:
        return None
    hm = re.search(r'(\d{1,2}):(\d{2})', t)
    hour, minute = (int(hm.group(1)), int(hm.group(2))) if hm else (12, 0)

    if 'сегодня' in t or 'today' in t:
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if 'вчера' in t or 'yesterday' in t:
        d = now - timedelta(days=1)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0)

    dm = re.search(
        r'(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?(?:\s+в\s+(\d{1,2}):(\d{2}))?',
        t,
    )
    if dm:
        day_num = int(dm.group(1))
        mon_key = dm.group(2)[:3]
        year = int(dm.group(3)) if dm.group(3) else now.year
        if dm.group(4):
            hour, minute = int(dm.group(4)), int(dm.group(5))
        month = MONTHS_RU.get(mon_key)
        if month:
            try:
                d = date(year, month, day_num)
                if not dm.group(3) and d > now.date():
                    d = date(year - 1, month, day_num)
                return datetime.combine(d, datetime.min.time()).replace(
                    hour=hour, minute=minute,
                )
            except ValueError:
                pass

    dm2 = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?:\s+(\d{1,2}):(\d{2}))?', t)
    if dm2:
        d, m = int(dm2.group(1)), int(dm2.group(2))
        y = int(dm2.group(3))
        if y < 100:
            y += 2000
        if dm2.group(4):
            hour, minute = int(dm2.group(4)), int(dm2.group(5))
        try:
            return datetime(y, m, d, hour, minute)
        except ValueError:
            pass
    return None


def _parse_post_date_from_block(post_block):
    for pattern in (
        r'data-date=["\'](\d+)["\']',
        r'data-time=["\'](\d+)["\']',
        r'rel=["\'](\d+)["\']',
        r'class="wcommunity_post_date"[^>]*>([^<]+)<',
        r'class="rel_date[^"]*"[^>]*>([^<]+)<',
        r'class="post_date[^"]*"[^>]*>([^<]+)<',
        r'class="wall_post_date[^"]*"[^>]*>([^<]+)<',
    ):
        m = re.search(pattern, post_block, re.I | re.S)
        if not m:
            continue
        if m.lastindex and m.group(1).isdigit():
            dt = _date_from_unix(m.group(1))
            if dt:
                return _format_post_date(dt)
        else:
            dt = _parse_relative_ru(html_lib.unescape(m.group(1)))
            if dt:
                return _format_post_date(dt)
    return None


def _normalize_image_url(url):
    url = html_lib.unescape(url or '').strip()
    if not url or url.startswith('data:'):
        return ''
    if url.startswith('//'):
        url = 'https:' + url
    url = url.split(' 2x')[0].strip()
    low = url.lower()
    if any(x in low for x in (
        '/dist/', '.js', 'polyfill', 'runtime.', '/images/', 'emoji',
        'blank.gif', 'fav_logo', 'loader_nav',
    )):
        return ''
    if '.doc' in low or '.xls' in low or '.pdf' in low:
        return ''
    if 'userapi.com' in low or 'vkuserphoto.ru' in low or 'mycdn.me' in low:
        return url
    if re.search(r'\.(?:jpg|jpeg|png|webp)(?:\?|$)', low):
        return url
    return ''


def _extract_image_url(post_block):
    block = html_lib.unescape(post_block or '')
    candidates = []
    for pattern in _IMAGE_URL_PATTERNS:
        for m in re.finditer(pattern, block, re.I):
            url = _normalize_image_url(m.group(1))
            if url:
                candidates.append(url)
    if not candidates:
        return ''
    for c in candidates:
        if '/impg/' in c or '/photo' in c or 'sized' in c:
            return c
    return candidates[0]


def _http_get_text(url, headers):
    resp = requests.get(url, timeout=25, headers=headers)
    resp.raise_for_status()
    if 'widget_community.php' in url or 'vk.com/' in url or 'm.vk.com' in url:
        resp.encoding = 'cp1251'
    elif resp.encoding in (None, 'ISO-8859-1'):
        resp.encoding = resp.apparent_encoding or 'utf-8'
    return resp.text


def _default_headers():
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5',
        'Referer': VK_GROUP_URL,
    }


def _parse_wall_html(page_html, seen_urls, items, limit):
    """Parse wpt-* blocks from one HTML page; append to items up to limit."""
    if not page_html:
        return 0
    post_ids = []
    for match in re.findall(r'id="wpt-(-?\d+_\d+)"', page_html):
        if match not in post_ids:
            post_ids.append(match)
    added = 0
    for raw_id in post_ids:
        if len(items) >= limit:
            break
        owner_id, post_id = raw_id.split('_', 1)
        owner_id = owner_id.lstrip('-')
        post_url = f'https://vk.com/{VK_GROUP_DOMAIN}?w=wall-{VK_GROUP_ID}_{post_id}'
        if post_url in seen_urls:
            continue
        marker = f'id="wpt-{owner_id}_{post_id}"'
        start = page_html.find(marker)
        if start < 0:
            marker_alt = f'id="wpt-{raw_id}"'
            start = page_html.find(marker_alt)
        if start < 0:
            continue
        next_start = page_html.find('id="wpt-', start + 10)
        if next_start < 0:
            next_start = min(len(page_html), start + 60000)
        post_block = page_html[start:next_start]
        txt_match = re.search(r'class="wall_post_text"[^>]*>(.*?)</div>', post_block, re.S)
        text_raw = txt_match.group(1) if txt_match else ''
        text_clean = re.sub(r'<br\s*/?>', '\n', text_raw, flags=re.I)
        text_clean = re.sub(r'<[^>]+>', ' ', text_clean)
        text_clean = html_lib.unescape(text_clean)
        text_clean = re.sub(r'\s+', ' ', text_clean).strip()
        if not text_clean:
            continue
        image_url = _extract_image_url(post_block)
        if not image_url:
            continue
        post_date = _parse_post_date_from_block(post_block)
        if not post_date:
            continue
        seen_urls.add(post_url)
        items.append({
            'title': text_clean[:140] or 'Новость колледжа',
            'date': post_date,
            'summary': text_clean if len(text_clean) <= 700 else text_clean[:700].rstrip() + '...',
            'url': post_url,
            'image_url': image_url,
        })
        added += 1
    return added


def fetch_vk_news_scrape(limit=NEWS_CACHE_SIZE):
    """Scrape VK group wall: widget first, then mobile offset pages."""
    headers = _default_headers()
    items = []
    seen_urls = set()
    last_err = None

    widget_url = (
        f'https://vk.com/widget_community.php?app=0&width=500px&_ver=1'
        f'&gid={VK_GROUP_ID}&mode=4&color1=FFFFFF&color2=2B587A&color3=5B7FA6'
    )
    for url in (widget_url, VK_GROUP_URL, f'https://m.vk.com/{VK_GROUP_DOMAIN}'):
        if len(items) >= limit:
            break
        try:
            html = _http_get_text(url, headers)
            if html and ('wpt-' in html or 'wall_post_text' in html):
                _parse_wall_html(html, seen_urls, items, limit)
        except Exception as exc:
            last_err = str(exc)

    for offset in range(10, VK_WALL_MAX_OFFSET + 1, VK_WALL_PAGE_SIZE):
        if len(items) >= limit:
            break
        url = f'https://m.vk.com/{VK_GROUP_DOMAIN}?offset={offset}'
        try:
            html = _http_get_text(url, headers)
            if not html or ('wpt-' not in html and 'wall_post_text' not in html):
                break
            before = len(items)
            _parse_wall_html(html, seen_urls, items, limit)
            if len(items) == before:
                break
        except Exception as exc:
            last_err = str(exc)
            break

    if not items:
        return [], last_err or 'Не удалось извлечь новости с фото из VK.'
    return items[:limit], None


def fetch_vk_news_from_public_page(limit=NEWS_CACHE_SIZE):
    """Legacy alias."""
    return fetch_vk_news_scrape(limit=limit)


def fetch_vk_news(limit=NEWS_CACHE_SIZE):
    items, err = fetch_vk_news_scrape(limit=limit)
    if items:
        with get_db() as conn:
            merge_news_cache(conn, items)
    return items, err


def _cache_is_stale(last_fetch, ttl_seconds=NEWS_CACHE_TTL_SECONDS):
    if not last_fetch:
        return True
    now = datetime.now(timezone.utc)
    ts = last_fetch
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() >= ttl_seconds


def refresh_vk_news_cache(force=False, limit=NEWS_CACHE_SIZE):
    """Scrape VK wall hourly; merge into DB (max 10 posts). Returns (updated, error)."""
    with _news_refresh_lock:
        try:
            with get_db() as conn:
                last = get_last_news_fetch(conn)
                if not force and not _cache_is_stale(last):
                    return False, None
        except Exception as exc:
            return False, str(exc)

        items, err = fetch_vk_news_scrape(limit=limit)
        if not items:
            return False, err or 'Нет новостей с фото'
        try:
            with get_db() as conn:
                merge_news_cache(conn, items, max_items=NEWS_CACHE_SIZE)
            return True, None
        except Exception as exc:
            return False, str(exc)


def schedule_news_refresh_async(force=False):
    def _run():
        try:
            refresh_vk_news_cache(force=force)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def _normalize_post_url(url):
    m = re.search(r'wall-(\d+)_(\d+)', (url or '').strip())
    if m:
        return f'https://vk.com/{VK_GROUP_DOMAIN}?w=wall-{m.group(1)}_{m.group(2)}'
    return url


def load_cached_news_formatted(limit=NEWS_CACHE_SIZE):
    try:
        with get_db() as conn:
            rows = load_news_cache(conn, limit)
            return [{
                'title': r['title'], 'date': r['post_date'],
                'summary': r['summary'],
                'url': _normalize_post_url(r['post_url']),
                'image_url': r['image_url'],
            } for r in rows if r.get('image_url')]
    except Exception:
        return []


def get_news_for_site(limit=NEWS_CACHE_SIZE):
    schedule_news_refresh_async()
    return load_cached_news_formatted(limit), None
