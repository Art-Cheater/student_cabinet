#!/usr/bin/env python3
"""Download schedule Excel attachments from VK wall posts."""
import os
import re
import sys
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import requests

VK_GROUP_DOMAIN = os.getenv('VK_GROUP_DOMAIN', 'kollegevyatsu')
VK_API_VERSION = '5.199'
SCHEDULE_PATTERN = re.compile(
    r'Расписание\s+учебных\s+занятий\s+с\s+(\d{2})\.(\d{2})',
    re.IGNORECASE,
)


def get_token():
    token = os.getenv('VK_ACCESS_TOKEN', '').strip()
    if not token:
        print('Set VK_ACCESS_TOKEN in .env')
        sys.exit(1)
    return token


def wall_posts(token, count=30):
    resp = requests.get(
        'https://api.vk.com/method/wall.get',
        params={
            'domain': VK_GROUP_DOMAIN,
            'count': count,
            'filter': 'owner',
            'access_token': token,
            'v': VK_API_VERSION,
        },
        timeout=30,
    )
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(data['error'].get('error_msg', data['error']))
    return data.get('response', {}).get('items', [])


def download_doc(token, doc):
    url = doc.get('url')
    if not url:
        owner_id = doc['owner_id']
        doc_id = doc['id']
        r = requests.get(
            'https://api.vk.com/method/docs.getById',
            params={
                'docs': f'{owner_id}_{doc_id}',
                'access_token': token,
                'v': VK_API_VERSION,
            },
            timeout=30,
        ).json()
        items = r.get('response', [])
        if items:
            url = items[0].get('url')
    if not url:
        return None
    file_resp = requests.get(url, timeout=120)
    file_resp.raise_for_status()
    ext = doc.get('ext', 'xlsx') or 'xlsx'
    fd, path = tempfile.mkstemp(suffix=f'.{ext}')
    os.close(fd)
    with open(path, 'wb') as f:
        f.write(file_resp.content)
    return path


def run_parser(xlsx_path, effective_from, post_id):
    script = os.path.join(ROOT, 'schedule_parser', 'parse_schedule.py')
    cmd = [
        sys.executable, script, xlsx_path,
        '--effective-from', effective_from,
        '--source', 'vk',
        '--vk-post-id', str(post_id),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT)


def main():
    token = get_token()
    posts = wall_posts(token)
    found = 0
    for post in posts:
        text = (post.get('text') or '').strip()
        m = SCHEDULE_PATTERN.search(text)
        if not m:
            continue
        effective_from = f'{m.group(1)}.{m.group(2)}'
        post_id = post.get('id')
        for att in post.get('attachments', []):
            if att.get('type') != 'doc':
                continue
            doc = att.get('doc', {})
            ext = (doc.get('ext') or '').lower()
            if ext not in ('xlsx', 'xls'):
                continue
            path = download_doc(token, doc)
            if not path:
                continue
            try:
                print(f'Parsing post {post_id}, effective {effective_from}')
                run_parser(path, effective_from, post_id)
                found += 1
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
    print(f'Done. Processed {found} schedule post(s).')


if __name__ == '__main__':
    main()
