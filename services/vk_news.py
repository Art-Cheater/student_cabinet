import html as html_lib
import os
import re
from datetime import date, datetime, timedelta

import requests

from db.connection import get_db
from db.queries.content import load_news_cache, save_news_cache

VK_GROUP_URL = 'https://vk.com/kollegevyatsu?act=s&id=85060840'
VK_GROUP_ID = 85060840
VK_GROUP_DOMAIN = os.getenv('VK_GROUP_DOMAIN', 'kollegevyatsu')
VK_API_VERSION = '5.199'


def get_vk_access_token():
    try:
        from db.connection import get_db
        from db.queries.settings import get_setting
        with get_db() as conn:
            db_token = get_setting(conn, 'vk_access_token', '').strip()
            if db_token:
                return db_token
    except Exception:
        pass
    return os.getenv('VK_ACCESS_TOKEN', '').strip()


MONTHS_RU = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5,
    'июн': 6, 'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
}


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
    """Parse VK relative dates: сегодня в 12:30, вчера, 5 июн в 14:00."""
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


def _fetch_post_dates_wall_getbyid(owner_id, post_ids):
    """Try VK API for post timestamps (works with or without token for public walls)."""
    if not post_ids:
        return {}
    posts_param = ','.join(f'{owner_id}_{pid}' for pid in post_ids)
    params = {'posts': posts_param, 'v': VK_API_VERSION}
    token = get_vk_access_token()
    if token:
        params['access_token'] = token
    try:
        resp = requests.get(
            'https://api.vk.com/method/wall.getById', params=params, timeout=10,
        )
        data = resp.json()
        if 'error' in data:
            return {}
        result = {}
        for post in data.get('response', {}).get('items', []):
            pid = post.get('id')
            ts = post.get('date')
            if pid and ts:
                result[str(pid)] = _format_post_date(datetime.fromtimestamp(ts))
        return result
    except Exception:
        return {}


def fetch_vk_news_from_public_page(limit=10):
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5',
        'Referer': 'https://vk.com/',
    }
    widget_url = (
        f'https://vk.com/widget_community.php?app=0&width=320px&_ver=1'
        f'&gid={VK_GROUP_ID}&mode=4&color1=FFFFFF&color2=2B587A&color3=5B7FA6'
    )
    page_html = None
    last_err = None
    for url in (widget_url, widget_url.replace('https://vk.com/', 'https://m.vk.com/')):
        try:
            resp = requests.get(url, timeout=25, headers=headers)
            resp.raise_for_status()
            resp.encoding = 'cp1251'
            page_html = resp.text
            if page_html and 'wpt-' in page_html:
                break
            last_err = 'VK вернул страницу без постов.'
        except Exception as exc:
            last_err = str(exc)
    if not page_html:
        return [], last_err or 'Не удалось получить VK widget.'

    post_ids = []
    for match in re.findall(r'id="wpt-(-?\d+_\d+)"', page_html):
        if match not in post_ids:
            post_ids.append(match)
    items = []
    used_image_urls = set()
    pending_dates = []
    for raw_id in post_ids:
        marker = f'id="wpt-{raw_id.lstrip("-")}"'
        start = page_html.find(marker)
        if start < 0:
            continue
        next_start = page_html.find('id="wpt-', start + len(marker))
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
        img_match = re.search(
            r'https://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?', post_block, re.I
        )
        image_url = img_match.group(0) if img_match else None
        if not image_url or image_url in used_image_urls:
            continue
        owner_id, post_id = raw_id.split('_', 1)
        post_date = _parse_post_date_from_block(post_block)
        item = {
            'title': text_clean[:140] or 'Новость колледжа',
            'date': post_date,
            'summary': text_clean if len(text_clean) <= 700 else text_clean[:700].rstrip() + '...',
            'url': f'https://vk.com/wall{owner_id}_{post_id}',
            'image_url': image_url,
            '_owner_id': owner_id,
            '_post_id': post_id,
        }
        items.append(item)
        if not post_date:
            pending_dates.append((len(items) - 1, owner_id, post_id))
        used_image_urls.add(image_url)
        if len(items) >= limit:
            break

    if pending_dates and items:
        by_owner = {}
        for idx, oid, pid in pending_dates:
            by_owner.setdefault(oid, []).append((idx, pid))
        for oid, pairs in by_owner.items():
            api_dates = _fetch_post_dates_wall_getbyid(
                oid, [p[1] for p in pairs],
            )
            for idx, pid in pairs:
                if api_dates.get(str(pid)):
                    items[idx]['date'] = api_dates[str(pid)]

    for item in items:
        if not item.get('date'):
            item['date'] = datetime.now().strftime('%d.%m.%Y %H:%M')
        item.pop('_owner_id', None)
        item.pop('_post_id', None)

    if not items:
        return [], 'Не удалось извлечь новости из VK widget.'
    return items[:limit], None


def fetch_vk_news(limit=10):
    vk_access_token = get_vk_access_token()
    try:
        params = {
            'domain': VK_GROUP_DOMAIN,
            'count': limit,
            'filter': 'owner',
            'v': VK_API_VERSION,
        }
        if vk_access_token:
            params['access_token'] = vk_access_token
        response = requests.get(
            'https://api.vk.com/method/wall.get', params=params, timeout=10
        )
        response.raise_for_status()
    except Exception as exc:
        scraped, scraped_err = fetch_vk_news_from_public_page(limit=limit)
        if scraped:
            with get_db() as conn:
                save_news_cache(conn, scraped)
            return scraped, 'Лента загружена из публичной страницы VK (без токена).'
        return [], f'Не удалось загрузить новости: {scraped_err or exc}.'

    data = response.json()
    if 'error' in data:
        error = data.get('error', {})
        message = error.get('error_msg', 'ошибка VK API')
        if error.get('error_code') == 5:
            scraped, scraped_err = fetch_vk_news_from_public_page(limit=limit)
            if scraped:
                with get_db() as conn:
                    save_news_cache(conn, scraped)
                return scraped, 'Лента из публичной страницы VK.'
            return [], message
        return [], message

    news_items = []
    for post in data.get('response', {}).get('items', []):
        text = (post.get('text') or '').strip()
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0][:140] if lines else 'Новость колледжа'
        summary = text if len(text) <= 700 else text[:700].rstrip() + '...'
        post_date = datetime.fromtimestamp(post.get('date', 0)).strftime('%d.%m.%Y %H:%M')
        post_id = post.get('id')
        if post_id is None:
            continue
        post_url = f'https://vk.com/{VK_GROUP_DOMAIN}?w=wall-{abs(post.get("owner_id", 0))}_{post_id}'
        image_url = None
        for attachment in post.get('attachments', []):
            if attachment.get('type') != 'photo':
                continue
            sizes = attachment.get('photo', {}).get('sizes', [])
            if sizes:
                image_url = sizes[-1].get('url')
                break
        if not image_url:
            continue
        news_items.append({
            'title': title, 'date': post_date, 'summary': summary,
            'url': post_url, 'image_url': image_url,
        })
    if not news_items:
        return [], 'В ВК не найдено публикаций с фото.'
    with get_db() as conn:
        save_news_cache(conn, news_items)
    return news_items, None


def load_cached_news_formatted(limit=10):
    try:
        with get_db() as conn:
            rows = load_news_cache(conn, limit)
            return [{
                'title': r['title'], 'date': r['post_date'],
                'summary': r['summary'], 'url': r['post_url'],
                'image_url': r['image_url'],
            } for r in rows]
    except Exception:
        return []
