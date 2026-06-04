def save_news_cache(conn, news_items):
    conn.execute('DELETE FROM content.vk_news_cache')
    for item in news_items:
        post_id = abs(hash(item['url'])) % (2**63 - 1)
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


def load_news_cache(conn, limit=10):
    return conn.execute('''
        SELECT title, post_date, summary, post_url, image_url
        FROM content.vk_news_cache
        ORDER BY fetched_at DESC, id DESC
        LIMIT %s
    ''', (limit,)).fetchall()


def list_faq(conn):
    return conn.execute('SELECT * FROM content.faq ORDER BY id').fetchall()
