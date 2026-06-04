"""Общежития ВятГУ — парсинг страницы и официальные контакты."""
import re

from bs4 import BeautifulSoup

from parsers.vyatsu_buildings import normalize_address

DORMS_URL = 'https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html'

# Контакты с https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html
DORMS_OFFICIAL = [
    {
        'number': 1,
        'address': 'г. Киров, Октябрьский пр-кт, д. 113',
        'phone': '(8332) 64-45-21',
        'contact_person': 'Новоселова Татьяна Алексеевна',
    },
    {
        'number': 2,
        'address': 'г. Киров, ул. Ломоносова, 12',
        'phone': '(8332) 53-08-94',
        'contact_person': 'Шибанова Людмила Алексеевна',
    },
    {
        'number': 3,
        'address': 'г. Киров, ул. Ломоносова, 12а',
        'phone': '(8332) 53-05-81',
        'contact_person': 'Кулигина Дания Закиевна',
    },
    {
        'number': 4,
        'address': 'г. Киров, ул. Ломоносова, 16а, корп. 1',
        'phone': '(8332) 53-00-72',
        'contact_person': 'Бахшалиева Сакина Мирза-Гусейновна',
    },
    {
        'number': 5,
        'address': 'г. Киров, ул. Ломоносова, 16а, корп. 2',
        'phone': '(8332) 53-04-74',
        'contact_person': 'Тимшина Валентина Николаевна',
    },
    {
        'number': 6,
        'address': 'г. Киров, ул. Ленина, 113а',
        'phone': '(8332) 67-63-06',
        'contact_person': 'Соболева Елена Сергеевна',
    },
    {
        'number': 7,
        'address': 'г. Киров, ул. Ленина, 198/5',
        'phone': '(8332) 35-64-00',
        'contact_person': 'Бачуринская Татьяна Геннадьевна',
    },
    {
        'number': 8,
        'address': 'г. Киров, ул. Свободы, 133',
        'phone': '(8332) 37-37-40',
        'contact_person': 'Шарафутдинова Динара Гайсовна',
    },
]

# Блоки в HTML: <strong>общежитие №N</strong>&nbsp;адрес&nbsp;тел. (8332)&nbsp;...
DORM_HTML_RE = re.compile(
    r'<strong>\s*общежитие\s*№\s*(\d+)\s*</strong>\s*'
    r'(?:&nbsp;|\s)+'
    r'([^<]+?)\s*'
    r'(?:&nbsp;)*\s*тел\.?\s*'
    r'\((\d{4})\)\s*(?:&nbsp;)?\s*([\d\-]+)',
    re.I | re.S,
)
FIO_AFTER_PHONE_RE = re.compile(
    r'>([А-ЯЁ][а-яё\-]+\s+[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ][а-яё\-]+(?:\s+[А-ЯЁ][а-яё\-]+)?)<',
)


def _entry_from_official(row):
    return {
        'number': row['number'],
        'name': f'Общежитие №{row["number"]}',
        'address': row['address'],
        'phone': row['phone'],
        'contact_person': row['contact_person'],
        'contact_role': 'Заведующая',
        'image_url': '',
        'kind': 'dorm',
    }


def parse_dorm_images(html):
    """Фото из таблицы на странице."""
    soup = BeautifulSoup(html, 'html.parser')
    images = {}
    for img in soup.find_all('img', src=re.compile(r'/uploads/image/')):
        parent = img.find_parent('td') or img.find_parent('div')
        if not parent:
            continue
        text = parent.get_text(' ', strip=True)
        m = re.search(r'Общежитие\s*№\s*(\d+)', text, re.I)
        if not m:
            continue
        src = img.get('src') or ''
        if src.startswith('/'):
            src = 'https://www.vyatsu.ru' + src
        images[int(m.group(1))] = src
    return images


def parse_dorms_contacts_html(html):
    """Контакты из HTML (дополняет официальный список)."""
    found = {}
    for m in DORM_HTML_RE.finditer(html):
        num = int(m.group(1))
        addr = normalize_address(f'г. Киров, {m.group(2).replace("&nbsp;", " ").strip()}')
        phone = f'({m.group(3)}) {m.group(4).strip()}'.replace('\xa0', ' ')
        chunk = html[m.end(): m.end() + 280]
        person = ''
        fm = FIO_AFTER_PHONE_RE.search(chunk)
        if fm:
            person = fm.group(1).strip()
        found[num] = {
            'address': addr,
            'phone': phone[:64],
            'contact_person': person[:255] if person else None,
        }
    return found


def parse_dorms_page(html):
    """Все 8 общежитий: официальные контакты + фото с сайта."""
    images = parse_dorm_images(html)
    html_contacts = parse_dorms_contacts_html(html)
    entries = {}
    for row in DORMS_OFFICIAL:
        e = _entry_from_official(row)
        num = e['number']
        if num in images:
            e['image_url'] = images[num]
        extra = html_contacts.get(num)
        if extra:
            if extra.get('address'):
                e['address'] = extra['address']
            if extra.get('phone'):
                e['phone'] = extra['phone']
            if extra.get('contact_person'):
                e['contact_person'] = extra['contact_person']
        entries[num] = e
    return [entries[n] for n in sorted(entries)]
