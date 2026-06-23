"""CSRF-защита, ограничение попыток входа и базовые security-заголовки."""
import os
import secrets
import time
from collections import defaultdict
from threading import Lock

from flask import abort, request, session

CSRF_SESSION_KEY = '_csrf_token'
CSRF_FORM_FIELD = 'csrf_token'
CSRF_HEADER = 'X-CSRF-Token'

LOGIN_MAX_ATTEMPTS = int(os.getenv('LOGIN_MAX_ATTEMPTS', '5'))
LOGIN_WINDOW_SECONDS = int(os.getenv('LOGIN_WINDOW_SECONDS', '300'))
LOGIN_LOCKOUT_SECONDS = int(os.getenv('LOGIN_LOCKOUT_SECONDS', '900'))

_login_lock = Lock()
_login_attempts = defaultdict(list)


def ensure_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf():
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        return
    expected = session.get(CSRF_SESSION_KEY)
    if not expected:
        abort(400, 'Сессия истекла. Обновите страницу и попробуйте снова.')
    token = request.form.get(CSRF_FORM_FIELD) or request.headers.get(CSRF_HEADER)
    if not token or not secrets.compare_digest(token, expected):
        abort(400, 'Неверный CSRF-токен. Обновите страницу и попробуйте снова.')


def _client_ip():
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return forwarded or request.remote_addr or 'unknown'


def _prune_attempts(ip, now):
    window_start = now - LOGIN_WINDOW_SECONDS
    attempts = _login_attempts.get(ip, [])
    attempts = [ts for ts in attempts if ts >= window_start]
    _login_attempts[ip] = attempts
    return attempts


def check_login_allowed():
    now = time.time()
    ip = _client_ip()
    with _login_lock:
        attempts = _prune_attempts(ip, now)
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            oldest = attempts[0]
            retry_after = int(LOGIN_LOCKOUT_SECONDS - (now - oldest))
            if retry_after > 0:
                minutes = max(1, (retry_after + 59) // 60)
                abort(
                    429,
                    f'Слишком много неудачных попыток входа. Повторите через {minutes} мин.',
                )
            _login_attempts[ip] = []


def record_failed_login():
    now = time.time()
    ip = _client_ip()
    with _login_lock:
        attempts = _prune_attempts(ip, now)
        attempts.append(now)
        _login_attempts[ip] = attempts


def clear_login_attempts():
    ip = _client_ip()
    with _login_lock:
        _login_attempts.pop(ip, None)


def apply_security_headers(response):
    if response is None:
        return response
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(self), geolocation=(self)')
    if request.is_secure:
        response.headers.setdefault(
            'Strict-Transport-Security',
            'max-age=31536000; includeSubDomains',
        )
    return response
