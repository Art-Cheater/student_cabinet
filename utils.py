import hashlib
import re
import secrets

import bcrypt
from werkzeug.security import check_password_hash as werkzeug_check_password_hash


def get_course_from_group(group_name):
    numbers = re.findall(r'\d+', group_name or '')
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
    return re.fullmatch(r'[A-Za-zА-Яа-яЁё\- ]+', value) is not None


def is_card_number_valid(card_number):
    return re.fullmatch(r'\d+', (card_number or '').strip()) is not None


def hash_card_number(card_number):
    return hashlib.sha256((card_number or '').strip().encode('utf-8')).hexdigest()


def check_password(password, hashed):
    if not hashed:
        return False
    try:
        if bcrypt.checkpw(password.encode(), hashed.encode()):
            return True
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        if werkzeug_check_password_hash(hashed, password):
            return True
    except (ValueError, TypeError):
        pass
    return secrets.compare_digest(
        password.encode('utf-8', errors='surrogatepass'),
        str(hashed).encode('utf-8', errors='surrogatepass'),
    )


def normalize_building_number(value):
    value = (value or '').strip()
    match = re.search(r'(\d+)', value)
    return match.group(1) if match else ''


def validate_office_room(value):
    return re.fullmatch(r'\d+-\d+', (value or '').strip()) is not None


def format_fio(last_name=None, first_name=None, middle_name=None, row=None):
    """Фамилия Имя Отчество."""
    if row is not None:
        last_name = row.get('last_name')
        first_name = row.get('first_name')
        middle_name = row.get('middle_name')
    parts = [
        (last_name or '').strip(),
        (first_name or '').strip(),
        (middle_name or '').strip(),
    ]
    return ' '.join(p for p in parts if p).strip() or 'Пользователь'
