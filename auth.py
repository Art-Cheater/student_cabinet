from functools import wraps

from flask import flash, redirect, session, url_for


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в систему.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                flash('Войдите в систему.')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Недостаточно прав.')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def redirect_after_login(role):
    if role == 'admin':
        return redirect(url_for('admin_panel'))
    return redirect(url_for('index'))


def populate_session(user_row, group_name=None):
    session['user_id'] = user_row['id']
    session['role'] = user_row['role_code']
    session['user_name'] = format_display_name(user_row)
    session['group'] = group_name
    session['group_id'] = user_row.get('group_id')
    session['student_id'] = user_row.get('student_id')
    session['course'] = user_row.get('course')


def format_display_name(user_row):
    if not user_row:
        return 'Пользователь'
    first = (user_row.get('first_name') or '').strip()
    middle = (user_row.get('middle_name') or '').strip()
    last = (user_row.get('last_name') or '').strip()
    full = ' '.join(p for p in (first, middle, last) if p).strip()
    return full or 'Пользователь'
