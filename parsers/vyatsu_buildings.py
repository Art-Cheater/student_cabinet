"""Parse учебные корпуса с официальной страницы ВятГУ."""
import re
from collections import defaultdict

from bs4 import BeautifulSoup

BUILDINGS_URL = (
    'https://www.vyatsu.ru/studentu-1/pervokursniku/'
    'adresa-i-telefonyi-uchebnyih-korpusov-fakul-tetov.html'
)

CORP_NUM_RE = re.compile(r'(?:Учебный\s+)?[Кк]орпус\s*№\s*(\d+)', re.I)
PHONE_RE = re.compile(r'(?:Тел\.?|Тел:)\s*(\(\d{4}\)[\s\d\-]+)', re.I)


def extract_address_phone(text):
    """Адрес от индекса 610xxx до «Тел.»."""
    phone_m = PHONE_RE.search(text)
    phone = phone_m.group(1).strip().replace('\xa0', ' ') if phone_m else ''
    head = text[: phone_m.start()] if phone_m else text
    addr_m = re.search(
        r'(\d{6}\s*,.+)$',
        head.strip(),
        re.I | re.S,
    )
    address = normalize_address(addr_m.group(1) if addr_m else '')
    return address, phone


def normalize_address(raw):
    addr = re.sub(r'\s+', ' ', (raw or '')).strip()
    addr = re.sub(r',\s*Тел\..*$', '', addr, flags=re.I)
    return addr[:500]


def _building_name(num, text):
    if num == 9 and 'спорт' in text.lower():
        return 'Учебный корпус №9 (спорткомплекс)'
    if num == 19 and ('спортивн' in text.lower() or 'уск' in text.lower()):
        return 'Учебный корпус №19 (учебно-спортивный комплекс)'
    if num >= 20:
        return f'Корпус №{num}'
    return f'Учебный корпус №{num}'


def _parse_cell(td):
    text = td.get_text(' ', strip=True)
    if not CORP_NUM_RE.search(text):
        return None
    m_num = CORP_NUM_RE.search(text)
    num = int(m_num.group(1))
    address, phone = extract_address_phone(text)
    img = td.find('img', src=re.compile(r'/uploads/image/'))
    image_url = ''
    if img and img.get('src'):
        image_url = img['src']
        if image_url.startswith('/'):
            image_url = 'https://www.vyatsu.ru' + image_url
    return {
        'number': num,
        'name': _building_name(num, text)[:255],
        'address': address,
        'phone': phone[:64],
        'image_url': image_url,
        'kind': 'building',
    }


def parse_buildings_page(html):
    """Все корпуса из таблицы (включая №21–22 без фото)."""
    soup = BeautifulSoup(html, 'html.parser')
    entries = {}
    for td in soup.find_all('td'):
        row = _parse_cell(td)
        if not row:
            continue
        num = row['number']
        prev = entries.get(num)
        if not prev:
            entries[num] = row
            continue
        # Объединяем: не затираем фото и более длинный адрес
        if not prev.get('image_url') and row.get('image_url'):
            prev['image_url'] = row['image_url']
        if len(row.get('address') or '') > len(prev.get('address') or ''):
            prev['address'] = row['address']
        if not prev.get('phone') and row.get('phone'):
            prev['phone'] = row['phone']
    return sorted(entries.values(), key=lambda e: e['number'])


def parse_building_institute_notes(html):
    """
    Блок «Институты и факультеты»: директора, деканаты, кабинеты.
    Несколько записей на один корпус объединяются.
    """
    soup = BeautifulSoup(html, 'html.parser')
    notes = defaultdict(list)
    seen_lines = defaultdict(set)

    for strong in soup.find_all('strong'):
        title = strong.get_text(strip=True)
        m = CORP_NUM_RE.search(title)
        if not m:
            continue
        num = int(m.group(1))
        node = strong.parent
        if not node:
            continue
        for sib in node.find_next_siblings():
            line = sib.get_text(' ', strip=True)
            if not line:
                continue
            if re.match(r'^(ИНСТИТУТ|Факультет)\b', line, re.I):
                break
            if re.match(r'^КОЛЛЕДЖ\b', line, re.I):
                continue
            if CORP_NUM_RE.search(line) and notes[num]:
                break
            if re.search(
                r'(Директор|Деканат|декан|Тел\.|Телефон|E-mail|Email|каб\.)',
                line,
                re.I,
            ):
                if line not in seen_lines[num]:
                    seen_lines[num].add(line)
                    notes[num].append(line)
            if len(notes[num]) >= 12:
                break

    return {num: '\n'.join(lines) for num, lines in notes.items() if lines}
