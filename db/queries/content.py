import re

NEWS_CACHE_SIZE = 10


def _valid_news_item(item):
    return bool(
        item
        and item.get('image_url')
        and str(item.get('image_url', '')).strip()
        and item.get('date')
        and str(item.get('date', '')).strip()
        and item.get('url')
    )


def vk_post_id_from_url(url):
    """Stable id from wall-85060840_9411 URL."""
    m = re.search(r'wall-(\d+)_(\d+)', (url or '').strip())
    if not m:
        return None
    owner, post = int(m.group(1)), int(m.group(2))
    return owner * 10**10 + post


def dedupe_news_cache_by_url(conn):
    """Remove duplicate rows with the same post_url (legacy hash post_id vs wall id)."""
    dup_urls = conn.execute('''
        SELECT post_url FROM content.vk_news_cache
        WHERE post_url IS NOT NULL AND TRIM(post_url) <> ''
        GROUP BY post_url HAVING COUNT(*) > 1
    ''').fetchall()
    for row in dup_urls:
        url = row['post_url'].strip()
        canonical = vk_post_id_from_url(url)
        if canonical is not None:
            kept = conn.execute(
                '''
                SELECT id FROM content.vk_news_cache
                WHERE post_url = %s AND post_id = %s
                ORDER BY fetched_at DESC
                LIMIT 1
                ''',
                (url, canonical),
            ).fetchone()
            if kept:
                conn.execute(
                    'DELETE FROM content.vk_news_cache WHERE post_url = %s AND id <> %s',
                    (url, kept['id']),
                )
                continue
        conn.execute('''
            DELETE FROM content.vk_news_cache
            WHERE post_url = %s AND id NOT IN (
                SELECT id FROM content.vk_news_cache
                WHERE post_url = %s
                ORDER BY fetched_at DESC
                LIMIT 1
            )
        ''', (url, url))


def merge_news_cache(conn, news_items, max_items=NEWS_CACHE_SIZE):
    """Upsert scraped posts; keep at most max_items newest by post_id."""
    valid = [i for i in (news_items or []) if _valid_news_item(i)]
    if not valid:
        return 0
    for item in valid:
        post_id = vk_post_id_from_url(item['url'])
        if post_id is None:
            continue
        conn.execute('''
            INSERT INTO content.vk_news_cache
            (post_id, title, summary, post_date, post_url, image_url, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (post_id) DO UPDATE SET
                title = EXCLUDED.title, summary = EXCLUDED.summary,
                post_date = EXCLUDED.post_date, post_url = EXCLUDED.post_url,
                image_url = EXCLUDED.image_url, fetched_at = NOW()
        ''', (
            post_id, item['title'], item['summary'],
            item['date'], item['url'], item['image_url'],
        ))
    dedupe_news_cache_by_url(conn)
    purge_news_without_images(conn)
    conn.execute('''
        DELETE FROM content.vk_news_cache
        WHERE id NOT IN (
            SELECT id FROM content.vk_news_cache
            ORDER BY post_id DESC
            LIMIT %s
        )
    ''', (max_items,))
    return len(valid)


def save_news_cache(conn, news_items):
    """Legacy alias."""
    return merge_news_cache(conn, news_items)


def purge_news_without_images(conn):
    conn.execute('''
        DELETE FROM content.vk_news_cache
        WHERE image_url IS NULL OR TRIM(image_url) = ''
           OR post_date IS NULL OR TRIM(post_date) = ''
    ''')


def get_last_news_fetch(conn):
    row = conn.execute(
        'SELECT MAX(fetched_at) AS ts FROM content.vk_news_cache',
    ).fetchone()
    return row['ts'] if row else None


def load_news_cache(conn, limit=NEWS_CACHE_SIZE):
    dedupe_news_cache_by_url(conn)
    purge_news_without_images(conn)
    return conn.execute('''
        SELECT title, post_date, summary, post_url, image_url
        FROM content.vk_news_cache
        WHERE image_url IS NOT NULL AND TRIM(image_url) <> ''
          AND post_date IS NOT NULL AND TRIM(post_date) <> ''
        ORDER BY post_id DESC
        LIMIT %s
    ''', (limit,)).fetchall()


def list_faq(conn):
    return conn.execute('SELECT * FROM content.faq ORDER BY id').fetchall()
