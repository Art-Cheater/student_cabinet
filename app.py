from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort, send_from_directory
import sqlite3
import os
import re
import secrets
import requests
import bcrypt
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash as werkzeug_check_password_hash
import subprocess
import sys
import json
import hashlib
import html as html_lib
from urllib.parse import quote_plus

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

STUDENTS_DB = 'students.db'
CONTENT_DB = 'content.db'
SCHEDULE_DB = 'schedule.db'
VK_GROUP_URL = 'https://vk.com/kollegevyatsu?act=s&id=85060840'
VK_GROUP_ID = 85060840
VK_GROUP_DOMAIN = os.getenv('VK_GROUP_DOMAIN', 'kollegevyatsu')
VK_API_VERSION = '5.199'
VK_CACHE_TTL_SECONDS = int(os.getenv('VK_CACHE_TTL', '3600'))
VYATSU_DORMS_URL = 'https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html'
VYATSU_BUILDINGS_URL = 'https://www.vyatsu.ru/studentu-1/pervokursniku/adresa-i-telefonyi-uchebnyih-korpusov-fakul-tetov.html'
WEEK_DAYS_RU = [
    'Понедельник',
    'Вторник',
    'Среда',
    'Четверг',
    'Пятница',
    'Суббота',
    'Воскресенье',
]
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = bcrypt.hashpw(
    os.getenv('ADMIN_PASSWORD', 'admin123').encode(), bcrypt.gensalt()
).decode()
UPLOADS_DIR = os.path.join('schedule_parser', 'uploads')
PRIVATE_STORAGE_DIR = os.path.join('private_storage')
PHOTO_UPLOADS_DIR = os.path.join(PRIVATE_STORAGE_DIR, 'student_cards')
ALLOWED_EXTENSIONS = {'xlsx'}
ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
VK_TOKEN_FILE = 'vk_token.txt'
VYATSU_DORMS = [
    {'name': 'Общежитие №1', 'address': 'Октябрьский пр-кт, д. 113', 'phone': '(8332) 64-45-21', 'image_url': 'https://www.vyatsu.ru/uploads/image/1710/7obschezhitie1_(2).jpg', 'lat': 58.6032080, 'lon': 49.6454819},
    {'name': 'Общежитие №2', 'address': 'ул. Ломоносова, 12', 'phone': '(8332) 53-08-94', 'image_url': 'https://www.vyatsu.ru/uploads/image/1607/obsch_2.jpg', 'lat': 58.6068444, 'lon': 49.6139144},
    {'name': 'Общежитие №3', 'address': 'ул. Ломоносова, 12а', 'phone': '(8332) 53-05-81', 'image_url': 'https://www.vyatsu.ru/uploads/image/1607/obsch_3.jpg', 'lat': 58.6068849, 'lon': 49.6148883},
    {'name': 'Общежитие №4', 'address': 'ул. Ломоносова, 16а, корп. 1', 'phone': '(8332) 53-00-72', 'image_url': 'https://www.vyatsu.ru/uploads/image/1607/obsch_4.jpg', 'lat': 58.6051361, 'lon': 49.6163525},
    {'name': 'Общежитие №5', 'address': 'ул. Ломоносова, 16а, корп. 2', 'phone': '(8332) 53-04-74', 'image_url': 'https://www.vyatsu.ru/uploads/image/1607/obsch_5.jpg', 'lat': 58.6052361, 'lon': 49.6164525},
    {'name': 'Общежитие №6', 'address': 'ул. Ленина, 113а', 'phone': '(8332) 67-63-06', 'image_url': 'https://www.vyatsu.ru/uploads/image/1607/6.jpg', 'lat': 58.5903303, 'lon': 49.6815571},
    {'name': 'Общежитие №7', 'address': 'ул. Ленина, 198/5', 'phone': '(8332) 35-64-00', 'image_url': 'https://www.vyatsu.ru/uploads/image/1710/1obschezhitie2_(1).jpg', 'lat': 58.5672059, 'lon': 49.6881641},
    {'name': 'Общежитие №8', 'address': 'ул. Свободы, 133', 'phone': '(8332) 37-37-40', 'image_url': 'https://www.vyatsu.ru/uploads/image/1710/8obschezhitie2.jpg', 'lat': 58.5904838, 'lon': 49.6770740},
]

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(PHOTO_UPLOADS_DIR, exist_ok=True)
VYATSU_BUILDINGS = [
    {'name': 'Корпус №1', 'address': 'ул. Московская, д. 36', 'phone': '(8332) 70-82-67', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_9401.jpg', 'lat': 58.6032080, 'lon': 49.6454819},
    {'name': 'Корпус №2', 'address': 'ул. Московская, д. 39', 'phone': '(8332) 70-82-27', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_9369.jpg', 'lat': 58.6032080, 'lon': 49.6454819},
    {'name': 'Корпус №3', 'address': 'ул. Московская, д. 29', 'phone': '(8332) 64-56-27', 'image_url': 'https://www.vyatsu.ru/uploads/image/1308/3_korp_m.jpg', 'lat': 58.6029204, 'lon': 49.6319040},
    {'name': 'Корпус №4', 'address': 'ул. Защитников Отечества, д. 76', 'phone': '(8332) 64-55-29', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1168.jpg', 'lat': 58.5893228, 'lon': 49.6657860},
    {'name': 'Корпус №5 (Колледж)', 'address': 'ул. Владимирская, д. 55', 'phone': '(8332) 64-26-24', 'image_url': 'https://www.vyatsu.ru/uploads/image/1708/img_5209.jpg', 'lat': 58.6133600, 'lon': 49.6662800},
    {'name': 'Корпус №6', 'address': 'Студенческий проезд, д. 9', 'phone': '(8332) 53-17-50', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1206.jpg', 'lat': 58.5995466, 'lon': 49.6181253},
    {'name': 'Корпус №8', 'address': 'Студенческий проезд, д. 11', 'phone': '(8332) 53-04-45', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1198.jpg', 'lat': 58.5995466, 'lon': 49.6181253},
    {'name': 'Корпус №10', 'address': 'ул. Ломоносова, д. 18а', 'phone': '(8332) 53-04-75', 'image_url': 'https://www.vyatsu.ru/uploads/image/1604/10korpus_(3).jpg', 'lat': 58.6123792, 'lon': 49.6033178},
    {'name': 'Корпус №13', 'address': 'ул. Красноармейская, д. 26', 'phone': '(8332) 37-27-48', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1106.jpg', 'lat': 58.5919495, 'lon': 49.6851055},
    {'name': 'Корпус №14', 'address': 'ул. Ленина, д. 111', 'phone': '(8332) 67-86-20', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1113.jpg', 'lat': 58.5907946, 'lon': 49.6807405},
    {'name': 'Корпус №15', 'address': 'ул. Ленина, д. 198', 'phone': '(8332) 35-62-68', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_1393.jpg', 'lat': 58.5660900, 'lon': 49.6865449},
    {'name': 'Корпус №19', 'address': 'ул. Орловская, д. 12', 'phone': '(8332) 70-81-18', 'image_url': 'https://www.vyatsu.ru/uploads/image/2411/img_9638.jpg', 'lat': 58.5959175, 'lon': 49.6668991},
]

def init_students_db():
    conn = sqlite3.connect(STUDENTS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            group_name TEXT,
            student_id TEXT,
            course INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            card_number_hash TEXT UNIQUE NOT NULL,
            card_number_last4 TEXT,
            photo_path TEXT,
            face_photo_path TEXT,
            study_form TEXT,
            issue_date TEXT,
            course_number INTEGER,
            verification_signature TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    # Миграции для старых схем students.db
    for sql in (
        "ALTER TABLE student_cards ADD COLUMN face_photo_path TEXT",
        "ALTER TABLE student_cards ADD COLUMN verification_signature TEXT",
        "ALTER TABLE student_cards ADD COLUMN card_number_hash TEXT",
        "ALTER TABLE student_cards ADD COLUMN card_number_last4 TEXT",
    ):
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass
    # Миграция users: full_name -> last_name / first_name / middle_name.
    user_columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
    needs_users_rebuild = 'full_name' in user_columns
    if needs_users_rebuild:
        old_users = cursor.execute('''
            SELECT id, email, password_hash, full_name, group_name, student_id, course
            FROM users
        ''').fetchall()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                last_name TEXT NOT NULL,
                first_name TEXT NOT NULL,
                middle_name TEXT,
                group_name TEXT,
                student_id TEXT,
                course INTEGER
            )
        ''')
        for row in old_users:
            last_name, first_name, middle_name = split_full_name(row[3])
            cursor.execute('''
                INSERT INTO users_new
                (id, email, password_hash, last_name, first_name, middle_name, group_name, student_id, course)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row[0], row[1], row[2], last_name, first_name, middle_name, row[4], row[5], row[6]
            ))
        cursor.execute('DROP TABLE users')
        cursor.execute('ALTER TABLE users_new RENAME TO users')
    else:
        for sql in (
            "ALTER TABLE users ADD COLUMN last_name TEXT",
            "ALTER TABLE users ADD COLUMN first_name TEXT",
            "ALTER TABLE users ADD COLUMN middle_name TEXT",
        ):
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()

def init_content_db():
    conn = sqlite3.connect(CONTENT_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vk_news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER UNIQUE,
            title TEXT,
            summary TEXT,
            post_date TEXT,
            post_url TEXT,
            image_url TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            source_url TEXT
        )
    ''')
    try:
        cursor.execute("ALTER TABLE faq ADD COLUMN source_url TEXT")
    except sqlite3.OperationalError:
        pass
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            teacher_name TEXT,
            date TEXT,
            time TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    faqs = [
        (
            "Как поступить в ВятГУ?",
            "Подробные правила приема, сроки и перечень документов смотрите на официальной странице приемной кампании.",
            "https://www.vyatsu.ru/abitur/"
        ),
        (
            "Где найти расписание занятий?",
            "Расписание и учебные сервисы доступны в личном кабинете и в разделах для обучающихся на официальном сайте.",
            "https://www.vyatsu.ru/studentu-1/"
        ),
        (
            "Где посмотреть адреса и телефоны учебных корпусов?",
            "Актуальный список корпусов, адресов и телефонов размещен на официальной странице университета.",
            "https://www.vyatsu.ru/studentu-1/pervokursniku/adresa-i-telefonyi-uchebnyih-korpusov-fakul-tetov.html"
        ),
        (
            "Где посмотреть информацию об общежитиях?",
            "Информация по общежитиям, адресам и контактам доступна на официальной странице ВятГУ.",
            "https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html"
        ),
        (
            "Куда обращаться по вопросам обучения и сервисов студента?",
            "Контакты подразделений и общие каналы связи опубликованы на странице контактов ВятГУ.",
            "https://www.vyatsu.ru/kontaktyi.html"
        ),
        (
            "Где смотреть официальные новости университета?",
            "Официальные новости и объявления публикуются на сайте ВятГУ в разделе новостей.",
            "https://www.vyatsu.ru/internet-gazeta/"
        ),
    ]
    for q, a, src in faqs:
        exists = cursor.execute("SELECT id FROM faq WHERE question = ?", (q,)).fetchone()
        if exists:
            cursor.execute(
                "UPDATE faq SET answer = ?, source_url = ? WHERE id = ?",
                (a, src, exists[0])
            )
        else:
            cursor.execute(
                "INSERT INTO faq (question, answer, source_url) VALUES (?, ?, ?)",
                (q, a, src)
            )
    conn.commit()
    conn.close()

def init_user_db():
    # Совместимость со старыми тестами/импортами.
    init_students_db()
    init_content_db()
    init_schedule_db()


def init_schedule_db():
    """Таблицы расписания в schedule.db (на новом сервере файла может не быть)."""
    from schedule_parser.schedule_schema import apply_schedule_schema

    conn = sqlite3.connect(SCHEDULE_DB)
    try:
        apply_schedule_schema(conn)
    finally:
        conn.close()


def get_students_db():
    conn = sqlite3.connect(STUDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_content_db():
    conn = sqlite3.connect(CONTENT_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_schedule_db():
    conn = sqlite3.connect(SCHEDULE_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_course_from_group(group_name):
    numbers = re.findall(r'\d+', group_name)
    for num in numbers:
        if len(num) >= 2:
            first_digit = int(str(num)[0])
            if 1 <= first_digit <= 4:
                return first_digit
    return 1

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def is_password_allowed(password):
    if not password:
        return False
    return re.fullmatch(r'[A-Za-z0-9]+', password) is not None

def is_name_part_valid(value, allow_empty=False):
    value = (value or '').strip()
    if allow_empty and not value:
        return True
    # Разрешаем только буквы (кириллица/латиница), пробел и дефис.
    return re.fullmatch(r"[A-Za-zА-Яа-яЁё\- ]+", value) is not None


def split_full_name(full_name):
    parts = [part for part in (full_name or '').split() if part]
    if not parts:
        return 'Неизвестно', 'Студент', None
    if len(parts) == 1:
        return parts[0], parts[0], None
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], ' '.join(parts[2:])


def format_user_display_name(user_row):
    if not user_row:
        return 'Пользователь'
    last_name = (row_value(user_row, 'last_name', '') or '').strip()
    first_name = (row_value(user_row, 'first_name', '') or '').strip()
    middle_name = (row_value(user_row, 'middle_name', '') or '').strip()
    full = ' '.join(part for part in (first_name, middle_name, last_name) if part).strip()
    return full or 'Пользователь'

def is_card_number_valid(card_number):
    return re.fullmatch(r'\d+', (card_number or '').strip()) is not None

def row_value(row, key, default=None):
    if not row:
        return default
    try:
        return row[key]
    except Exception:
        return default

def extract_building_from_classroom(classroom):
    value = (classroom or '').strip()
    match = re.match(r'^(\d+)\s*[-–]', value)
    return match.group(1) if match else None

def normalize_building_number(value):
    value = (value or '').strip()
    match = re.search(r'(\d+)', value)
    return match.group(1) if match else ''

def hash_card_number(card_number):
    return hashlib.sha256((card_number or '').strip().encode('utf-8')).hexdigest()

def fetch_vk_news_from_public_page(limit=10):
    """Парсинг публичного виджета VK (без токена). На IP хостингов ВК часто отдаёт заглушку — тогда нужен VK_ACCESS_TOKEN."""
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5',
        'Referer': 'https://vk.com/',
        'Connection': 'keep-alive',
    }
    widget_url = (
        'https://vk.com/widget_community.php'
        '?app=0&width=320px&_ver=1'
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
            last_err = 'VK вернул страницу без постов (возможна блокировка IP хостинга).'
        except Exception as exc:
            last_err = str(exc)
            continue
    if not page_html:
        return [], last_err or 'Не удалось получить VK widget.'

    post_ids = []
    # Основной источник ID постов в виджете сейчас.
    for match in re.findall(r'id="wpt-(-?\d+_\d+)"', page_html):
        if match not in post_ids:
            post_ids.append(match)
        if len(post_ids) >= max(limit * 4, 30):
            break
    # Фолбэк для старой разметки.
    for match in re.findall(r'data-post-id="(-?\d+_\d+)"', page_html):
        if match not in post_ids:
            post_ids.append(match)
        if len(post_ids) >= max(limit * 5, 50):
            break

    items = []
    used_image_urls = set()
    for raw_id in post_ids:
        owner_id, post_id = raw_id.split('_', 1)
        post_link = f'https://vk.com/wall{owner_id}_{post_id}'

        # Берем строго HTML-блок конкретного поста, чтобы не путать контент соседних карточек.
        # В widget id блока обычно без ведущего минуса: wpt-85060840_1234
        marker = f'id="wpt-{raw_id.lstrip("-")}"'
        start = page_html.find(marker)
        if start < 0:
            continue
        next_start = page_html.find('id="wpt-', start + len(marker))
        if next_start < 0:
            next_start = min(len(page_html), start + 60000)
        post_block = page_html[start:next_start]

        date_zone_start = max(0, start - 1200)
        date_zone = page_html[date_zone_start:start + 500]
        date_match = re.search(rf'href="/wall{re.escape(raw_id)}"[^>]*>(.*?)</a>', date_zone, re.S)
        date_text = html_lib.unescape(re.sub(r'<[^>]+>', '', date_match.group(1))).strip() if date_match else ''

        txt_match = re.search(r'class="wall_post_text"[^>]*>(.*?)</div>', post_block, re.S)
        text_raw = txt_match.group(1) if txt_match else ''
        text_clean = re.sub(r'<br\s*/?>', '\n', text_raw, flags=re.I)
        text_clean = re.sub(r'<[^>]+>', ' ', text_clean)
        text_clean = html_lib.unescape(text_clean)
        text_clean = re.sub(r'\s+', ' ', text_clean).strip()
        if not text_clean:
            continue

        img_match = re.search(r'https://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?', post_block, re.I)
        image_url = img_match.group(0) if img_match else None

        # По требованию: только посты с фото.
        if not image_url:
            continue
        if image_url in used_image_urls:
            continue

        items.append({
            'title': text_clean[:140] or 'Новость колледжа',
            'date': date_text or datetime.now().strftime('%d.%m.%Y %H:%M'),
            'summary': text_clean if len(text_clean) <= 700 else text_clean[:700].rstrip() + '...',
            'url': post_link,
            'image_url': image_url,
        })
        used_image_urls.add(image_url)

        if len(items) >= limit:
            break

    if not items:
        return [], 'Не удалось извлечь новости из VK widget.'
    return items[:limit], None

def check_password(password, hashed):
    if not hashed:
        return False

    # Основной путь: bcrypt.
    try:
        if bcrypt.checkpw(password.encode(), hashed.encode()):
            return True
    except (ValueError, TypeError, AttributeError):
        # Поддержка старых форматов ниже.
        pass

    # Обратная совместимость со старыми хэшами werkzeug.
    try:
        if werkzeug_check_password_hash(hashed, password):
            return True
    except (ValueError, TypeError):
        pass

    # Последний fallback для очень старых plain-text записей.
    return secrets.compare_digest(
        password.encode('utf-8', errors='surrogatepass'),
        str(hashed).encode('utf-8', errors='surrogatepass'),
    )

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_photo_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


def save_private_student_photo(upload, user_id, prefix):
    if not upload or not upload.filename:
        return None, None
    if not allowed_photo_file(upload.filename):
        return None, 'Допустимые форматы фото: png, jpg, jpeg, gif, webp.'
    filename = secure_filename(upload.filename)
    if not filename:
        return None, 'Некорректное имя файла.'
    ext = filename.rsplit('.', 1)[1].lower()
    os.makedirs(PHOTO_UPLOADS_DIR, exist_ok=True)
    stored_rel_path = os.path.join(
        'student_cards',
        f'{prefix}_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.{ext}'
    )
    abs_path = os.path.join(PRIVATE_STORAGE_DIR, stored_rel_path)
    upload.save(abs_path)
    return stored_rel_path, None

def get_vk_access_token():
    env_token = os.getenv('VK_ACCESS_TOKEN', '').strip()
    if env_token:
        return env_token

    if os.path.exists(VK_TOKEN_FILE):
        try:
            with open(VK_TOKEN_FILE, 'r', encoding='utf-8') as file:
                for line in file:
                    candidate = line.strip()
                    if not candidate or candidate.startswith('#'):
                        continue
                    return candidate
        except OSError:
            return ''

    return ''

def update_schedule_from_excel(excel_path):
    parser_script = os.path.join('schedule_parser', 'parse_schedule.py')
    if not os.path.exists(parser_script):
        return False, 'Файл парсера расписания не найден.'

    try:
        result = subprocess.run(
            [sys.executable, parser_script, excel_path],
            capture_output=True,
            text=True,
            check=True
        )
        output = (result.stdout or '').strip()
        return True, output or 'Расписание успешно обновлено.'
    except subprocess.CalledProcessError as exc:
        error_output = (exc.stderr or exc.stdout or '').strip()
        return False, error_output or 'Ошибка запуска парсера расписания.'

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
            'https://api.vk.com/method/wall.get',
            params=params,
            timeout=10
        )
        response.raise_for_status()
    except Exception as exc:
        scraped, scraped_err = fetch_vk_news_from_public_page(limit=limit)
        if scraped:
            _save_news_to_cache(scraped)
            return scraped, 'Лента загружена из публичной страницы VK (без токена).'
        return [], f'Не удалось загрузить новости из ВК: {scraped_err or exc}.'

    data = response.json()
    if 'error' in data:
        error = data.get('error', {})
        error_code = error.get('error_code')
        message = error.get('error_msg', 'неизвестная ошибка VK API')
        if error_code == 5 or 'expired' in message.lower():
            scraped, scraped_err = fetch_vk_news_from_public_page(limit=limit)
            if scraped:
                _save_news_to_cache(scraped)
                return scraped, 'Лента загружена из публичной страницы VK (без токена).'
            return [], (
                f'Не удалось получить новости ВК: {scraped_err or message}. '
                'Новости не будут показаны, чтобы не выводить устаревшие данные.'
            )
        if error_code == 15:
            return [], 'VK отклонил доступ к стене группы.'
        return [], f'VK API вернул ошибку: {message}.'

    items = data.get('response', {}).get('items', [])
    news_items = []

    for post in items:
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
                if image_url:
                    break

        if not image_url:
            continue

        news_items.append({
            'title': title,
            'date': post_date,
            'summary': summary,
            'url': post_url,
            'image_url': image_url,
        })

    if not news_items:
        return [], 'В ВК не найдено публикаций с фото.'

    _save_news_to_cache(news_items)
    return news_items, None


def _save_news_to_cache(news_items):
    try:
        with get_content_db() as conn:
            # Храним актуальный снимок ленты, чтобы не копились старые дубли.
            conn.execute('DELETE FROM vk_news_cache')
            for item in news_items:
                # Стабильный ключ, чтобы не терять старые записи между перезапусками.
                post_id = int.from_bytes(item['url'].encode('utf-8'), 'little', signed=False) % (2**63 - 1)
                conn.execute('''
                    INSERT OR REPLACE INTO vk_news_cache
                    (post_id, title, summary, post_date, post_url, image_url, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    post_id,
                    item['title'],
                    item['summary'],
                    item['date'],
                    item['url'],
                    item['image_url'],
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ))
            # Удерживаем разумный размер кэша и сохраняем старые новости для fallback.
            conn.execute('''
                DELETE FROM vk_news_cache
                WHERE id NOT IN (
                    SELECT id
                    FROM vk_news_cache
                    ORDER BY fetched_at DESC, id DESC
                    LIMIT 200
                )
            ''')
            conn.commit()
    except Exception:
        pass


def _load_cached_news():
    try:
        with get_content_db() as conn:
            rows = conn.execute(
                'SELECT title, summary, post_date, post_url, image_url FROM vk_news_cache ORDER BY id DESC'
            ).fetchall()
            return [{
                'title': r['title'],
                'date': r['post_date'],
                'summary': r['summary'],
                'url': r['post_url'],
                'image_url': r['image_url'],
            } for r in rows]
    except Exception:
        return []

# Инициализируем БД и применяем миграции к существующим.
init_students_db()
init_content_db()
init_schedule_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        flash('Саморегистрация временно отключена. Обратитесь к администратору.')
        return redirect(url_for('login'))
    return render_template('register.html', groups=[], registration_disabled=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if not is_password_allowed(password):
            flash('Пароль может содержать только английские буквы и цифры')
            return render_template('login.html')
        with get_students_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE email = ?', 
                              (email,)).fetchone()
            if user and check_password(password, user['password_hash']):
                display_name = format_user_display_name(user)
                session['user_id'] = user['id']
                session['user_name'] = display_name
                session['group'] = user['group_name']
                session['student_id'] = user['student_id']
                session['course'] = user['course']
                flash(f'Добро пожаловать, {display_name}!')
                return redirect(url_for('dashboard'))
            else:
                flash('Неверный email или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', user=session)

@app.route('/schedule')
def schedule():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    group = session.get('group')
    schedule_data = []
    filter_mode = request.args.get('filter', 'week')
    if filter_mode not in ('week', 'today', 'tomorrow'):
        filter_mode = 'week'
    
    try:
        with get_schedule_db() as conn:
            rows = conn.execute('''
                SELECT 
                    l.day_name as day_of_week,
                    l.time_start as start_time,
                    l.time_end as end_time,
                    l.subject as discipline,
                    l.lesson_type,
                    t.name as teacher,
                    c.name as classroom,
                    l.lesson_number
                FROM lessons l
                JOIN groups g ON l.group_id = g.id
                LEFT JOIN teachers t ON l.teacher_id = t.id
                LEFT JOIN classrooms c ON l.classroom_id = c.id
                WHERE g.name = ?
                ORDER BY 
                    CASE l.day_name
                        WHEN 'Понедельник' THEN 1
                        WHEN 'Вторник' THEN 2
                        WHEN 'Среда' THEN 3
                        WHEN 'Четверг' THEN 4
                        WHEN 'Пятница' THEN 5
                        WHEN 'Суббота' THEN 6
                        ELSE 7
                    END,
                    l.lesson_number
            ''', (group,)).fetchall()
            schedule_data = [dict(row) for row in rows]
            for item in schedule_data:
                item['building_number'] = extract_building_from_classroom(item.get('classroom'))
    except Exception as e:
        print(f"Ошибка получения расписания: {e}")

    target_day = None
    if filter_mode == 'today':
        target_day = WEEK_DAYS_RU[datetime.now().weekday()]
    elif filter_mode == 'tomorrow':
        target_day = WEEK_DAYS_RU[(datetime.now() + timedelta(days=1)).weekday()]

    if target_day:
        schedule_data = [item for item in schedule_data if item['day_of_week'] == target_day]

    return render_template(
        'schedule.html',
        schedule=schedule_data,
        group=group,
        filter_mode=filter_mode,
    )

@app.route('/news')
def news():
    news_items, parse_error = fetch_vk_news(limit=10)
    if not news_items:
        cached = _load_cached_news()
        if cached:
            news_items = cached[:10]
            parse_error = parse_error or (
                'Не удалось получить свежие новости из ВК с этого сервера '
                '(у части хостингов VK режет запросы по IP). '
                'Показан последний сохранённый кэш. Для стабильной загрузки задайте VK_ACCESS_TOKEN '
                'в переменных окружения Render.'
            )

    return render_template(
        'news.html',
        news=news_items,
        source_url=VK_GROUP_URL,
        parse_error=parse_error,
    )

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if username == ADMIN_USERNAME and bcrypt.checkpw(password.encode(), ADMIN_PASSWORD_HASH.encode()):
            session['admin_logged_in'] = True
            flash('Вы вошли в админ-панель.')
            return redirect(url_for('admin_panel'))

        flash('Неверный логин или пароль администратора.')

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Вы вышли из админ-панели.')
    return redirect(url_for('admin_login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    parser_output = None
    uploaded_filename = None
    students = []

    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        if action == 'create_user':
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            group_name = request.form.get('group_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            first_name = request.form.get('first_name', '').strip()
            middle_name = request.form.get('middle_name', '').strip()
            card_number = request.form.get('card_number', '').strip()
            study_form = request.form.get('study_form', '').strip()
            issue_date = request.form.get('issue_date', '').strip()
            course_number = request.form.get('course_number', '').strip()
            face_photo = request.files.get('face_photo')

            if not email or not password or not group_name:
                flash('Заполните email, пароль и группу.')
                return redirect(url_for('admin_panel'))
            if not is_password_allowed(password):
                flash('Пароль: только английские буквы и цифры.')
                return redirect(url_for('admin_panel'))
            if not all([last_name, first_name, card_number, study_form, issue_date, course_number]):
                flash('Для студбилета заполните обязательные поля.')
                return redirect(url_for('admin_panel'))
            if not is_name_part_valid(last_name) or not is_name_part_valid(first_name) or not is_name_part_valid(middle_name, allow_empty=True):
                flash('Проверьте поля фамилии, имени и отчества.')
                return redirect(url_for('admin_panel'))
            if not is_card_number_valid(card_number):
                flash('Номер билета должен содержать только цифры.')
                return redirect(url_for('admin_panel'))
            if study_form not in ('Очная', 'Заочная'):
                flash('Форма обучения должна быть Очная или Заочная.')
                return redirect(url_for('admin_panel'))
            if course_number not in ('1', '2', '3', '4'):
                flash('Курс должен быть от 1 до 4.')
                return redirect(url_for('admin_panel'))
            try:
                issue_date = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                flash('Некорректная дата выдачи студбилета.')
                return redirect(url_for('admin_panel'))

            course = get_course_from_group(group_name)
            student_id = f"STU-{email.split('@')[0][:5]}-{course}"
            pwd_hash = hash_password(password)

            with get_students_db() as conn:
                existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
                if existing:
                    flash('Пользователь с таким email уже существует.')
                    return redirect(url_for('admin_panel'))
                conn.execute('''
                    INSERT INTO users (email, password_hash, last_name, first_name, middle_name, group_name, student_id, course)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (email, pwd_hash, last_name, first_name, middle_name or None, group_name, student_id, course))
                user_id = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']
                face_photo_path, face_photo_error = save_private_student_photo(face_photo, user_id, 'face')
                if face_photo_error:
                    conn.rollback()
                    flash(face_photo_error)
                    return redirect(url_for('admin_panel'))
                conn.execute('''
                    INSERT INTO student_cards
                    (user_id, last_name, first_name, middle_name, card_number_hash, card_number_last4,
                     photo_path, face_photo_path, study_form, issue_date, course_number, verification_signature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, last_name, first_name, middle_name, hash_card_number(card_number), card_number[-4:],
                      None, face_photo_path, study_form, issue_date, int(course_number), None))
                conn.commit()
            flash('Аккаунт и студбилет созданы.')
            return redirect(url_for('admin_panel'))
        elif action == 'update_student':
            user_id = request.form.get('user_id', '').strip()
            email = request.form.get('email', '').strip()
            group_name = request.form.get('group_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            first_name = request.form.get('first_name', '').strip()
            middle_name = request.form.get('middle_name', '').strip()
            card_number = request.form.get('card_number', '').strip()
            study_form = request.form.get('study_form', '').strip()
            issue_date = request.form.get('issue_date', '').strip()
            course_number = request.form.get('course_number', '').strip()
            face_photo = request.files.get('face_photo')

            if not user_id.isdigit():
                flash('Некорректный идентификатор студента.')
                return redirect(url_for('admin_panel'))
            if not email or not group_name or not all([last_name, first_name, study_form, issue_date, course_number]):
                flash('Заполните обязательные поля для обновления.')
                return redirect(url_for('admin_panel'))
            if not is_name_part_valid(last_name) or not is_name_part_valid(first_name) or not is_name_part_valid(middle_name, allow_empty=True):
                flash('Проверьте поля фамилии, имени и отчества.')
                return redirect(url_for('admin_panel'))
            if study_form not in ('Очная', 'Заочная'):
                flash('Форма обучения должна быть Очная или Заочная.')
                return redirect(url_for('admin_panel'))
            if course_number not in ('1', '2', '3', '4'):
                flash('Курс должен быть от 1 до 4.')
                return redirect(url_for('admin_panel'))
            try:
                issue_date = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                flash('Некорректная дата выдачи студбилета.')
                return redirect(url_for('admin_panel'))

            course = get_course_from_group(group_name)
            student_id = f"STU-{email.split('@')[0][:5]}-{course}"
            with get_students_db() as conn:
                existing = conn.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, int(user_id))).fetchone()
                if existing:
                    flash('Этот email уже используется другим пользователем.')
                    return redirect(url_for('admin_panel'))
                card = conn.execute(
                    'SELECT id, face_photo_path, card_number_hash, card_number_last4 FROM student_cards WHERE user_id = ?',
                    (int(user_id),)
                ).fetchone()
                if not card:
                    flash('Студбилет для выбранного пользователя не найден.')
                    return redirect(url_for('admin_panel'))
                face_photo_path = card['face_photo_path']
                card_number_hash = card['card_number_hash']
                card_number_last4 = card['card_number_last4']
                if card_number:
                    if not is_card_number_valid(card_number):
                        flash('Номер билета должен содержать только цифры.')
                        return redirect(url_for('admin_panel'))
                    card_number_hash = hash_card_number(card_number)
                    card_number_last4 = card_number[-4:]
                new_face_photo_path, face_photo_error = save_private_student_photo(face_photo, int(user_id), 'face')
                if face_photo_error:
                    flash(face_photo_error)
                    return redirect(url_for('admin_panel'))
                if new_face_photo_path:
                    face_photo_path = new_face_photo_path
                conn.execute('''
                    UPDATE users
                    SET email = ?, last_name = ?, first_name = ?, middle_name = ?, group_name = ?, student_id = ?, course = ?
                    WHERE id = ?
                ''', (email, last_name, first_name, middle_name or None, group_name, student_id, course, int(user_id)))
                conn.execute('''
                    UPDATE student_cards
                    SET last_name = ?, first_name = ?, middle_name = ?, card_number_hash = ?, card_number_last4 = ?,
                        face_photo_path = ?, study_form = ?, issue_date = ?, course_number = ?, verification_signature = NULL
                    WHERE user_id = ?
                ''', (last_name, first_name, middle_name or None, card_number_hash, card_number_last4,
                      face_photo_path, study_form, issue_date, int(course_number), int(user_id)))
                conn.commit()
            flash('Данные студента обновлены.')
            return redirect(url_for('admin_panel'))

        file = request.files.get('schedule_file')
        if not file or not file.filename:
            flash('Выберите Excel-файл для загрузки.')
            return redirect(url_for('admin_panel'))

        if not allowed_file(file.filename):
            flash('Допустим только файл формата .xlsx')
            return redirect(url_for('admin_panel'))

        os.makedirs(UPLOADS_DIR, exist_ok=True)
        safe_name = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_name = f'{timestamp}_{safe_name}'
        saved_path = os.path.join(UPLOADS_DIR, final_name)
        file.save(saved_path)
        uploaded_filename = final_name

        ok, message = update_schedule_from_excel(saved_path)
        parser_output = message
        if ok:
            flash('Расписание обновлено и опубликовано на сайте.')
        else:
            flash('Не удалось обновить расписание. См. детали ниже.')

    with get_students_db() as conn:
        students = conn.execute('''
            SELECT
                u.id as user_id,
                u.email,
                u.group_name,
                u.student_id,
                u.course,
                sc.card_number_last4,
                sc.study_form,
                sc.issue_date,
                sc.course_number,
                sc.last_name,
                sc.first_name,
                sc.middle_name,
                sc.face_photo_path,
                sc.id as card_id
            FROM users u
            LEFT JOIN student_cards sc ON sc.user_id = u.id
            ORDER BY u.id DESC
        ''').fetchall()

    return render_template(
        'admin_panel.html',
        parser_output=parser_output,
        uploaded_filename=uploaded_filename,
        students=students
    )

@app.route('/student_card', methods=['GET', 'POST'])
def student_card():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with get_students_db() as conn:
        user = conn.execute(
            'SELECT id, last_name, first_name, middle_name, group_name, student_id, course FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()
        card = conn.execute('''
            SELECT id, last_name, first_name, middle_name, card_number_last4,
                   face_photo_path, study_form, issue_date, course_number
            FROM student_cards
            WHERE user_id = ?
        ''', (session['user_id'],)).fetchone()
    if not user or not card:
        return render_template('student_card.html', card=None, user=session)
    fio = ' '.join([
        (card['last_name'] or '').strip(),
        (card['first_name'] or '').strip(),
        (card['middle_name'] or '').strip(),
    ]).strip()
    masked_number = f'****{card["card_number_last4"]}' if card['card_number_last4'] else 'скрыт'
    qr_payload = {
        'type': 'vyatsu_student_card',
        'student_id': row_value(user, 'student_id', ''),
        'fio': fio,
        'group': row_value(user, 'group_name', ''),
        'course': card['course_number'],
        'study_form': card['study_form'],
        'issue_date': card['issue_date'],
        'number': masked_number,
        'card_id': card['id'],
    }
    qr_url = (
        'https://api.qrserver.com/v1/create-qr-code/?size=260x260&data='
        + quote_plus(json.dumps(qr_payload, ensure_ascii=False))
    )
    return render_template('student_card.html', card=card, profile=user, fio=fio, masked_number=masked_number, qr_url=qr_url)

@app.route('/student_card/face/<int:card_id>')
def student_card_face_photo(card_id):
    if 'user_id' not in session and not session.get('admin_logged_in'):
        return redirect(url_for('login'))

    with get_students_db() as conn:
        card = conn.execute(
            'SELECT id, user_id, face_photo_path FROM student_cards WHERE id = ?',
            (card_id,)
        ).fetchone()

    is_owner = 'user_id' in session and card and card['user_id'] == session['user_id']
    is_admin = bool(session.get('admin_logged_in'))
    if not card or not card['face_photo_path'] or (not is_owner and not is_admin):
        abort(403)

    abs_photo_path = os.path.join(PRIVATE_STORAGE_DIR, card['face_photo_path'])
    if not os.path.exists(abs_photo_path):
        abort(404)

    return send_file(abs_photo_path, mimetype='image/jpeg', max_age=0)

@app.route('/map')
def map():
    yandex_key = os.getenv('YANDEX_MAPS_API_KEY', '')
    highlighted_building = normalize_building_number(request.args.get('building', ''))
    return render_template(
        'map.html',
        dorms=VYATSU_DORMS,
        buildings=VYATSU_BUILDINGS,
        dorms_source_url=VYATSU_DORMS_URL,
        buildings_source_url=VYATSU_BUILDINGS_URL,
        yandex_api_key=yandex_key,
        highlighted_building=highlighted_building,
    )

@app.route('/faq')
def faq():
    with get_content_db() as conn:
        faqs = conn.execute('SELECT * FROM faq').fetchall()
    return render_template('faq.html', faqs=faqs)

@app.route('/appointment', methods=['GET', 'POST'])
def appointment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        teacher = request.form['teacher']
        date = request.form['date']
        time = request.form['time']
        reason = request.form['reason']
        with get_content_db() as conn:
            conn.execute('''
                INSERT INTO appointments (user_id, teacher_name, date, time, reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['user_id'], teacher, date, time, reason))
            conn.commit()
        flash('Заявка на запись отправлена!')
        return redirect(url_for('appointment'))
    
    return render_template('appointment.html')


@app.route('/manifest.webmanifest')
def pwa_manifest():
    return send_from_directory(
        app.static_folder,
        'manifest.webmanifest',
        mimetype='application/manifest+json',
        max_age=3600,
    )


@app.route('/sw.js')
def pwa_service_worker():
    resp = send_from_directory(
        app.static_folder,
        'sw.js',
        mimetype='application/javascript',
    )
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    return resp


if __name__ == '__main__':
    # Локально: PORT не задан — 5000. На Render и др. хостингах: PORT задаёт платформа.
    # Слушать нужно 0.0.0.0, иначе внешний трафик до приложения не доходит.
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug)