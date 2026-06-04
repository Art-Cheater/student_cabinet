from functools import wraps

from flask import flash, redirect, session, url_for

from utils import format_fio


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
    if role == 'guard':
        return redirect(url_for('guard_scan'))
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
    return format_fio(row=user_row)
