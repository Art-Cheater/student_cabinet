import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request,
    send_file, send_from_directory, session, url_for,
)
from werkzeug.utils import secure_filename

load_dotenv()

from auth import format_display_name, login_required, populate_session, redirect_after_login, role_required
from db.connection import get_db
from db.queries.buildings import get_building_by_number, list_buildings
from db.queries.content import list_faq
from db.queries.groups import (
    get_group_by_name, get_or_create_group, list_groups, resolve_group_ids_by_names,
    search_groups,
)
from db.queries.office import (
    cancel_student_booking, create_booking, create_office_slot, delete_office_slot,
    get_available_slots_for_student, get_teacher_slots, list_slot_bookings,
    list_student_bookings, list_teacher_slots_summary, student_can_book_slot,
    student_slot_lesson_overlap, update_booking_status, update_office_slot,
)
from db.queries.qr_tokens import get_valid_token, issue_token
from db.queries.external_schedule import list_vyatsu_link_statuses
from db.queries.schedule import (
    get_classroom_events, get_group_schedule, get_schedule_events, get_latest_effective_from,
    get_teacher_lesson_events, list_classrooms, list_schedule_teacher_names,
)
from db.queries.slot_queue import (
    add_submission, delete_submission, get_queue_entry, get_submission,
    join_queue, leave_queue, list_queue, list_submissions, set_queue_passed,
)
from db.queries.teacher_events import (
    create_personal_event, delete_personal_event, list_personal_events,
)
from db.queries.users import (
    create_guard_user, create_student_user, create_teacher_user, delete_user, email_exists,
    get_student_profile, get_teacher_profile, get_teacher_public,
    get_user_by_email, get_user_by_id,
    count_students_admin, list_guards_admin, list_students_admin, list_teachers_admin,
    list_teachers_public,
    update_student, update_student_pass_number, update_teacher, update_teacher_pass_number,
    update_guard_user,
)
from parsers.vyatsu_teacher_busy import get_teacher_university_events
from services.calendar_events import (
    booking_to_event, group_slots_by_date, make_event_key, personal_event_to_event,
    slot_to_event,
)
from db.queries.calendar_meta import (
    attachment_event_keys_for_lookup,
    delete_attachment,
    delete_note,
    delete_note_file,
    get_attachment,
    get_note,
    get_note_file,
    insert_attachment,
    insert_note_file,
    list_attachments_for_event_keys,
    list_note_files_for_event,
    load_user_notes_map,
    resolve_slot_id_from_event_key,
    teacher_can_attach_to_event,
    upsert_note,
    user_can_download_attachment,
)
from services.calendar_nav import build_calendar_nav, date_range_for_nav
from services.vk_news import VK_GROUP_URL, get_news_for_site, refresh_vk_news_cache
from services.notifications import (
    get_vapid_public_key, notify_students_slot_material, notify_teacher_booking,
    notify_teacher_queue_join, notify_student_booking_rejected, push_enabled,
)
from db.queries.notifications import (
    count_unread_notifications, delete_push_subscription, list_notifications,
    mark_all_notifications_read, mark_notification_read, upsert_push_subscription,
)
from security import (
    apply_security_headers, check_login_allowed, clear_login_attempts,
    ensure_csrf_token, record_failed_login, validate_csrf,
)
from utils import (
    check_password, format_fio, get_course_from_group, hash_card_number, hash_password,
    is_card_number_valid, is_name_part_valid, is_password_allowed,
    normalize_building_number, validate_office_room,
)

app = Flask(__name__)


@app.template_filter('fio')
def template_fio(row):
    return format_fio(row=row)


def _qr_image_url(token):
    return url_for('api_qr_image', token=token)


def _refresh_user_qr(user_id, subject_type):
    with get_db() as conn:
        token, expires = issue_token(conn, user_id, subject_type)
    return _qr_image_url(token), token, expires


@app.route('/api/qr-image/<token>')
@login_required
def api_qr_image(token):
    role = session.get('role')
    if role not in ('student', 'teacher'):
        abort(403)
    with get_db() as conn:
        row = get_valid_token(conn, token)
        if not row or row['user_id'] != session['user_id']:
            abort(403)
    try:
        import io
        import qrcode
        gate_url = url_for('gate_entry', token=token, _external=True)
        img = qrcode.make(gate_url, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png', max_age=120)
    except Exception:
        abort(500)
_secret = os.getenv('FLASK_SECRET_KEY') or os.getenv('SECRET_KEY')
if not _secret or _secret in ('change-me-in-production', 'change-me-on-server'):
    _secret = os.urandom(32).hex()
    if not os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes'):
        print('WARNING: set FLASK_SECRET_KEY in .env — sessions reset on each restart without it.')
app.secret_key = _secret
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')


@app.before_request
def _security_before_request():
    if request.endpoint and request.endpoint.startswith('static'):
        return
    validate_csrf()


@app.after_request
def _security_after_request(response):
    return apply_security_headers(response)


@app.context_processor
def _inject_csrf():
    return dict(csrf_token=ensure_csrf_token)


@app.errorhandler(400)
def _bad_request(exc):
    msg = getattr(exc, 'description', None) or 'Неверный запрос.'
    if request.path.startswith('/api/'):
        return jsonify({'error': msg}), 400
    flash(msg)
    return redirect(request.referrer or url_for('index'))


@app.errorhandler(429)
def _too_many_requests(exc):
    msg = getattr(exc, 'description', None) or 'Слишком много попыток. Подождите и попробуйте снова.'
    if request.path.startswith('/api/'):
        return jsonify({'error': msg}), 429
    flash(msg)
    return redirect(url_for('login'))

UPLOADS_DIR = os.path.join('schedule_parser', 'uploads')
CALENDAR_ATTACHMENTS_DIR = os.path.join('uploads', 'calendar_attachments')
CALENDAR_NOTE_FILES_DIR = os.path.join('uploads', 'calendar_note_files')
SLOT_SUBMISSIONS_DIR = os.path.join('uploads', 'slot_submissions')
os.makedirs(CALENDAR_ATTACHMENTS_DIR, exist_ok=True)
os.makedirs(CALENDAR_NOTE_FILES_DIR, exist_ok=True)
os.makedirs(SLOT_SUBMISSIONS_DIR, exist_ok=True)


def _event_keys_from_events(events):
    keys = []
    for ev in events:
        k = ev.get('event_key') or ev.get('id')
        if k:
            keys.append(k)
    return keys


def _ensure_student_group_id(conn, user_id, student_profile, group_name):
    """Resolve group_id from profile or group name; persist if missing."""
    group_id = None
    if student_profile:
        group_id = student_profile.get('group_id')
        group_name = student_profile.get('group_name') or group_name
    if not group_id and group_name:
        group_id = get_or_create_group(conn, group_name)
        conn.execute(
            'UPDATE student_profiles SET group_id = %s WHERE user_id = %s',
            (group_id, user_id),
        )
    return group_id, group_name


def _serialize_teacher_files(attachments):
    seen = set()
    out = []
    for a in attachments:
        if a['id'] in seen:
            continue
        seen.add(a['id'])
        out.append({
            'id': a['id'],
            'name': a['original_name'],
            'url': url_for('api_calendar_attachment_download', attachment_id=a['id']),
        })
    return out
ALLOWED_CALENDAR_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', 'png', 'jpg', 'jpeg',
}


def _build_teacher_calendar_events(conn, teacher_user_id, date_from, date_to):
    profile = get_teacher_profile(conn, teacher_user_id)
    vyatsu_meta = None
    events = []
    if profile and profile.get('schedule_teacher_id'):
        events.extend(get_teacher_lesson_events(
            conn, profile['schedule_teacher_id'], date_from, date_to,
        ))
    slots = get_teacher_slots(conn, teacher_user_id, date_from, date_to)
    events.extend([slot_to_event(s) for s in slots])
    personal = list_personal_events(conn, teacher_user_id, date_from, date_to)
    events.extend([personal_event_to_event(p) for p in personal])
    if profile:
        uni_events, vyatsu_meta = get_teacher_university_events(
            conn, teacher_user_id,
            profile['last_name'], profile['first_name'], profile.get('middle_name'),
        )
        if isinstance(date_from, str):
            dfrom = date.fromisoformat(date_from[:10])
        else:
            dfrom = date_from
        if isinstance(date_to, str):
            dto = date.fromisoformat(date_to[:10])
        else:
            dto = date_to
        for ev in uni_events:
            day = (ev.get('start') or '')[:10]
            if day and dfrom.isoformat() <= day <= dto.isoformat():
                if not ev.get('event_key'):
                    ev['event_key'] = make_event_key(
                        'university_lesson',
                        start=ev.get('start', ''),
                        title=ev.get('title', ''),
                        fallback_id=ev.get('id'),
                    )
                events.append(ev)
    for ev in events:
        if ev.get('type') == 'lesson':
            ev['is_own_lesson'] = True
    return events, profile, vyatsu_meta
PRIVATE_STORAGE_DIR = os.path.join('private_storage')
PHOTO_UPLOADS_DIR = os.path.join(PRIVATE_STORAGE_DIR, 'student_cards')
ALLOWED_EXTENSIONS = {'xlsx'}
ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
WEEK_DAYS_RU = [
    'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье',
]
VYATSU_DORMS_URL = 'https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html'
VYATSU_BUILDINGS_URL = (
    'https://www.vyatsu.ru/studentu-1/pervokursniku/'
    'adresa-i-telefonyi-uchebnyih-korpusov-fakul-tetov.html'
)

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(PHOTO_UPLOADS_DIR, exist_ok=True)
os.makedirs(CALENDAR_ATTACHMENTS_DIR, exist_ok=True)


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
    stored_rel_path = os.path.join(
        'student_cards',
        f'{prefix}_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.{ext}',
    )
    abs_path = os.path.join(PRIVATE_STORAGE_DIR, stored_rel_path)
    upload.save(abs_path)
    return stored_rel_path, None


def update_schedule_from_excel(excel_path, effective_from=None):
    script = os.path.join('schedule_parser', 'parse_schedule.py')
    if not os.path.exists(script):
        return False, 'Файл парсера расписания не найден.'
    cmd = [sys.executable, script, excel_path]
    if effective_from:
        if isinstance(effective_from, date):
            ef = effective_from.strftime('%d.%m.%Y')
        else:
            ef = effective_from
        cmd.extend(['--effective-from', ef])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=os.environ.copy())
        return True, (result.stdout or '').strip() or 'Расписание успешно обновлено.'
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or '').strip() or 'Ошибка парсера.'


@app.route('/')
def index():
    news_preview, news_error = get_news_for_site(2)
    today_events = []
    if session.get('user_id') and session.get('role') == 'student':
        group = session.get('group')
        if group:
            try:
                with get_db() as conn:
                    today = date.today().isoformat()
                    events = get_schedule_events(conn, group, today, today)
                    today_events = sorted(events, key=lambda e: e.get('start', ''))[:2]
            except Exception:
                today_events = []
    return render_template(
        'index.html',
        news_preview=news_preview[:2],
        news_error=news_error,
        news_url=VK_GROUP_URL,
        user=session if session.get('user_id') else None,
        today_events=today_events,
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        flash('Саморегистрация отключена. Обратитесь к администратору.')
        return redirect(url_for('login'))
    return render_template('register.html', registration_disabled=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        check_login_allowed()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        if not is_password_allowed(password):
            flash('Пароль: только латиница и цифры.')
            return render_template('login.html')
        try:
            with get_db() as conn:
                user = get_user_by_email(conn, email)
                if user and check_password(password, user['password_hash']):
                    profile = None
                    group_name = None
                    if user['role_code'] == 'student':
                        profile = get_student_profile(conn, user['id'])
                        group_name = profile.get('group_name') if profile else None
                    populate_session({
                        **user,
                        'group_id': profile.get('group_id') if profile else None,
                        'student_id': profile.get('student_id') if profile else None,
                        'course': profile.get('course') if profile else None,
                    }, group_name)
                    clear_login_attempts()
                    flash(f'Добро пожаловать, {session["user_name"]}!')
                    return redirect_after_login(user['role_code'])
            record_failed_login()
            flash('Неверный email или пароль')
        except Exception:
            record_failed_login()
            flash('Ошибка входа. Проверьте подключение к базе данных.')
            return render_template('login.html')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы')
    return redirect(url_for('index'))


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
@role_required('student')
def dashboard():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'upload_photo':
            face_photo = request.files.get('face_photo')
            path, err = save_private_student_photo(face_photo, session['user_id'], 'face')
            if err:
                flash(err)
            elif path:
                with get_db() as conn:
                    conn.execute(
                        'UPDATE student_profiles SET face_photo_path = %s WHERE user_id = %s',
                        (path, session['user_id']),
                    )
                flash('Фото обновлено.')
            else:
                flash('Файл не выбран.')
            return redirect(url_for('dashboard'))
        if action == 'update_pass_number':
            abort(403)

    with get_db() as conn:
        user = get_student_profile(conn, session['user_id'])
    if not user or not user.get('card_number_hash'):
        return render_template('dashboard.html', card=None, user=session, profile=None)
    fio = format_fio(row=user)
    masked = f'****{user["card_number_last4"]}' if user.get('card_number_last4') else 'скрыт'
    return render_template(
        'dashboard.html',
        card=user,
        profile=user,
        fio=fio,
        masked_number=masked,
        user=session,
    )


@app.route('/schedule')
@login_required
def schedule_page():
    role = session.get('role')
    if role == 'teacher':
        return redirect(url_for('teacher_schedule'))
    if role != 'student':
        flash('Расписание доступно студентам и преподавателям.')
        return redirect(url_for('index'))
    
    group = session.get('group')
    default_week = None
    try:
        with get_db() as conn:
            ef = get_latest_effective_from(conn)
            if ef:
                default_week = ef.isoformat() if hasattr(ef, 'isoformat') else str(ef)
    except Exception:
        pass
    week_arg = request.args.get('week') or default_week
    cal = build_calendar_nav(
        request.args.get('view', 'week'),
        week_arg,
        request.args.get('day'),
        request.args.get('month'),
    )
    calendar_hint = None
    if not group:
        calendar_hint = 'Группа не указана в профиле. Обратитесь к администратору.'
    events = []
    if group:
        dfrom, dto = date_range_for_nav(cal)
        try:
            with get_db() as conn:
                events = get_schedule_events(conn, group, dfrom, dto)
                bookings = list_student_bookings(conn, session['user_id'])
                for b in bookings:
                    if b['status'] not in ('rejected', 'cancelled'):
                        events.append(booking_to_event(b))
        except Exception as exc:
            flash(f'Ошибка расписания: {exc}')

    notes_map = {}
    if events:
        try:
            with get_db() as conn:
                notes_map = load_user_notes_map(
                    conn, session['user_id'], _event_keys_from_events(events),
                )
        except Exception:
            pass

    return render_template(
        'schedule.html',
        group=group,
        cal=cal,
        events=events,
        notes_map=notes_map,
        calendar_hint=calendar_hint,
        calendar_base_url='schedule_page',
        extra_params={},
        show_calendar_legend=True,
    )


@app.route('/api/schedule/events')
@login_required
@role_required('student')
def api_schedule_events():
    group = session.get('group')
    date_from = request.args.get('from', date.today().isoformat())
    date_to = request.args.get('to', (date.today() + timedelta(days=7)).isoformat())
    with get_db() as conn:
        events = get_schedule_events(conn, group, date_from, date_to)
    return jsonify(events)


@app.route('/teacher/dashboard', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def teacher_dashboard():
    if request.method == 'POST' and request.form.get('action') == 'update_pass_number':
        pass_number = request.form.get('pass_number', '').strip()[:64]
        with get_db() as conn:
            update_teacher_pass_number(conn, session['user_id'], pass_number or None)
        flash('Номер пропуска сохранён.')
        return redirect(url_for('teacher_dashboard'))
    with get_db() as conn:
        profile = get_teacher_profile(conn, session['user_id'])
    return render_template(
        'teacher/dashboard.html',
        profile=dict(profile) if profile else None,
        user=session,
    )


@app.route('/teacher/slots')
@login_required
@role_required('teacher')
def teacher_slots():
    selected_slot = request.args.get('slot', type=int)
    with get_db() as conn:
        slots = list_teacher_slots_summary(conn, session['user_id'])
        bookings = []
        if selected_slot:
            bookings = list_slot_bookings(conn, selected_slot)
    return render_template(
        'teacher/slots.html',
        slots=slots,
        bookings=bookings,
        selected_slot=selected_slot,
        user=session,
    )


@app.route('/teacher/schedule')
@login_required
@role_required('teacher')
def teacher_schedule():
    cal = build_calendar_nav(
        request.args.get('view', 'week'),
        request.args.get('week'),
        request.args.get('day'),
        request.args.get('month'),
    )
    dfrom, dto = date_range_for_nav(cal)
    vyatsu_status = None
    notes_map = {}
    with get_db() as conn:
        events, profile, vyatsu_meta = _build_teacher_calendar_events(
            conn, session['user_id'], dfrom, dto,
        )
        groups = list_groups(conn)
        if vyatsu_meta:
            vyatsu_status = vyatsu_meta.get('link_status')
        if events:
            notes_map = load_user_notes_map(
                conn, session['user_id'], _event_keys_from_events(events),
            )
    return render_template(
        'teacher/schedule.html',
        cal=cal,
        events=events,
        notes_map=notes_map,
        groups=groups,
        calendar_base_url='teacher_schedule',
        extra_params={},
        user=session,
        show_calendar_legend=True,
        vyatsu_status=vyatsu_status,
    )


@app.route('/teacher/classrooms')
@login_required
@role_required('teacher')
def teacher_classroom_schedule():
    cal = build_calendar_nav(
        request.args.get('view', 'week'),
        request.args.get('week'),
        request.args.get('day'),
        request.args.get('month'),
    )
    dfrom, dto = date_range_for_nav(cal)
    classroom_id = request.args.get('classroom_id', type=int)
    notes_map = {}
    with get_db() as conn:
        classrooms = list_classrooms(conn)
        events = []
        if classroom_id:
            events = get_classroom_events(
                conn, classroom_id, dfrom, dto, session['user_id'],
            )
            if events:
                notes_map = load_user_notes_map(
                    conn, session['user_id'], _event_keys_from_events(events),
                )
    return render_template(
        'teacher/classroom_schedule.html',
        cal=cal,
        events=events,
        notes_map=notes_map,
        classrooms=classrooms,
        selected_classroom_id=classroom_id,
        calendar_base_url='teacher_classroom_schedule',
        extra_params={'classroom_id': classroom_id} if classroom_id else {},
        user=session,
        show_calendar_legend=True,
    )


@app.route('/api/teacher/personal-events', methods=['POST'])
@login_required
@role_required('teacher')
def api_teacher_personal_events():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'Заметка').strip()
    if not title:
        return jsonify({'error': 'Укажите заголовок'}), 400
    with get_db() as conn:
        eid = create_personal_event(
            conn,
            session['user_id'],
            data.get('event_date'),
            data.get('time_start'),
            data.get('time_end'),
            title,
            data.get('color'),
        )
    return jsonify({'ok': True, 'id': eid})


@app.route('/api/teacher/personal-events/<int:event_id>', methods=['DELETE'])
@login_required
@role_required('teacher')
def api_teacher_personal_event_delete(event_id):
    with get_db() as conn:
        ok = delete_personal_event(conn, event_id, session['user_id'])
    if not ok:
        return jsonify({'error': 'Не найдено'}), 404
    return jsonify({'ok': True})


@app.route('/api/teacher/slots', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def api_teacher_slots():
    if request.method == 'GET':
        date_from = request.args.get('from', date.today().isoformat())
        date_to = request.args.get('to', (date.today() + timedelta(days=14)).isoformat())
        with get_db() as conn:
            slots = get_teacher_slots(conn, session['user_id'], date_from, date_to)
        return jsonify([slot_to_event(s) for s in slots])

    data = request.get_json(silent=True) or request.form
    room = (data.get('room_display') or '').strip()
    if not validate_office_room(room):
        return jsonify({'error': 'Кабинет в формате 5-104'}), 400
    audience = data.get('audience_type', 'anyone')
    group_ids = []
    raw_ids = data.get('group_ids') or []
    if isinstance(raw_ids, str):
        group_ids = [int(x) for x in raw_ids.split(',') if str(x).strip().isdigit()]
    else:
        group_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    group_names = data.get('group_names') or []
    if isinstance(group_names, str):
        group_names = [group_names] if group_names.strip() else []
    try:
        with get_db() as conn:
            if group_names and not group_ids:
                group_ids = resolve_group_ids_by_names(conn, group_names)
    except Exception:
        pass
    if audience == 'one_group' and len(group_ids) != 1:
        return jsonify({'error': 'Выберите одну группу'}), 400
    if audience == 'multi_group' and not group_ids:
        return jsonify({'error': 'Выберите группы'}), 400
    try:
        with get_db() as conn:
            slot_date = data.get('slot_date')
            time_start = data.get('time_start')
            time_end = data.get('time_end')
            dfrom = slot_date
            dto = slot_date
            conflict_events, _, _ = _build_teacher_calendar_events(
                conn, session['user_id'], dfrom, dto,
            )
            confirm_overlap = data.get('confirm_overlap') in (
                True, 'true', '1', 1, 'yes',
            )
            slot_id = create_office_slot(
                conn,
                session['user_id'],
                slot_date,
                time_start,
                time_end,
                room,
                data.get('topic', 'Приём'),
                int(data.get('max_students', 1)),
                audience,
                group_ids,
                conflict_events=conflict_events,
                confirm_overlap=confirm_overlap,
                enable_queue=data.get('enable_queue') in (True, 'true', '1', 1, 'on'),
                enable_submission=data.get('enable_submission') in (
                    True, 'true', '1', 1, 'on',
                ),
            )
        return jsonify({'ok': True, 'slot_id': slot_id})
    except ValueError as exc:
        err = str(exc)
        if err == 'LESSON_OVERLAP':
            return jsonify({
                'error': 'В это время пара. Подтвердите создание слота.',
                'need_confirm': True,
            }), 409
        return jsonify({'error': err}), 409
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/teacher/slots/<int:slot_id>/bookings')
@login_required
@role_required('teacher')
def api_slot_bookings(slot_id):
    with get_db() as conn:
        rows = list_slot_bookings(conn, slot_id)
    return jsonify([dict(r) for r in rows])


@app.route('/api/teacher/bookings/<int:booking_id>', methods=['PATCH'])
@login_required
@role_required('teacher')
def api_booking_patch(booking_id):
    data = request.get_json(silent=True) or {}
    status = data.get('status', 'rejected')
    with get_db() as conn:
        ok, err = update_booking_status(conn, booking_id, session['user_id'], status)
        if ok and status == 'rejected':
            notify_student_booking_rejected(conn, booking_id)
    if not ok:
        return jsonify({'error': err or 'Не найдено'}), 404
    return jsonify({'ok': True})


@app.route('/api/groups/search')
@login_required
def api_groups_search():
    q = request.args.get('q', '').strip()
    with get_db() as conn:
        rows = search_groups(conn, q, limit=40)
    return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])


@app.route('/appointment')
@login_required
@role_required('student')
def appointment_list():
    with get_db() as conn:
        teachers = list_teachers_public(conn)
    return render_template('appointment.html', teachers=teachers)


@app.route('/appointment/mine')
@login_required
@role_required('student')
def appointment_mine():
    with get_db() as conn:
        bookings = list_student_bookings(conn, session['user_id'])
    return render_template('appointment_mine.html', bookings=bookings)


@app.route('/appointment/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def appointment_teacher(teacher_id):
    with get_db() as conn:
        teacher = get_teacher_public(conn, teacher_id)
        if not teacher:
            abort(404)
        student_profile = get_student_profile(conn, session['user_id'])
        group_id = None
        group_name = session.get('group')
        if student_profile:
            group_id, group_name = _ensure_student_group_id(
                conn, session['user_id'], student_profile, group_name,
            )
            session['group_id'] = group_id
            session['group'] = group_name
        if request.method == 'POST':
            slot_id = request.form.get('slot_id', type=int)
            if slot_id:
                can_book, block_reason = student_can_book_slot(
                    conn, slot_id, session['user_id'], group_id,
                )
                if can_book:
                    overlap_msg = student_slot_lesson_overlap(
                        conn, group_name, slot_id,
                    )
                    ok, err = create_booking(
                        conn, slot_id, session['user_id'], group_id,
                    )
                    if ok:
                        notify_teacher_booking(conn, slot_id, session['user_id'])
                        flash(
                            'Вы записаны. ' + (overlap_msg + ' ' if overlap_msg else '')
                            + 'Смотрите в расписании.',
                            'warning' if overlap_msg else '',
                        )
                    elif err == 'Вы уже записаны':
                        flash(err, 'warning')
                    else:
                        flash(err or 'Не удалось записаться')
                else:
                    flash(block_reason or 'Запись недоступна')
            else:
                flash('Не выбран слот')
            slot_row = conn.execute(
                'SELECT slot_date FROM office_slots WHERE id = %s',
                (request.form.get('slot_id', type=int),),
            ).fetchone() if request.form.get('slot_id', type=int) else None
            redir_date = None
            if slot_row and slot_row.get('slot_date'):
                sd = slot_row['slot_date']
                redir_date = sd.isoformat()[:10] if hasattr(sd, 'isoformat') else str(sd)[:10]
            return redirect(url_for(
                'appointment_teacher', teacher_id=teacher_id, date=redir_date,
            ))

        slots = get_available_slots_for_student(
            conn, teacher_id, group_id,
            date.today().isoformat(),
            (date.today() + timedelta(days=120)).isoformat(),
            student_user_id=session['user_id'],
        )
        slots_by_date = group_slots_by_date(slots)
        selected_date = request.args.get('date')
        if selected_date and selected_date not in slots_by_date:
            selected_date = None
        if not selected_date and slots_by_date:
            selected_date = next(iter(slots_by_date))
        day_slots = slots_by_date.get(selected_date, []) if selected_date else []
        slot_warnings = {}
        group_name = session.get('group')
        for s in slots:
            msg = student_slot_lesson_overlap(conn, group_name, s['id'])
            if msg:
                slot_warnings[s['id']] = msg

    return render_template(
        'appointment_teacher.html',
        teacher=teacher,
        slots_by_date=slots_by_date,
        selected_date=selected_date,
        day_slots=day_slots,
        slot_warnings=slot_warnings,
        teacher_id=teacher_id,
        group_id=group_id,
    )


@app.route('/admin', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_panel():
    tab = request.args.get('tab', 'students')
    if tab == 'help':
        return redirect(url_for('admin_panel', tab='guards'))
    parser_output = None
    uploaded_filename = None

    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'upload_schedule':
            file = request.files.get('schedule_file')
            if file and allowed_file(file.filename):
                os.makedirs(UPLOADS_DIR, exist_ok=True)
                final_name = f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{secure_filename(file.filename)}'
                saved_path = os.path.join(UPLOADS_DIR, final_name)
                file.save(saved_path)
                uploaded_filename = final_name
                ef_raw = request.form.get('effective_from', '').strip()
                ef = ef_raw if ef_raw else None
                ok, parser_output = update_schedule_from_excel(saved_path, ef)
                flash('Расписание обновлено.' if ok else 'Ошибка загрузки.')
            else:
                flash('Выберите .xlsx файл.')
            return redirect(url_for('admin_panel', tab='schedule'))

        if action == 'create_student':
            return _admin_create_student()
        if action == 'update_student':
            return _admin_update_student()
        if action == 'delete_user':
            uid = request.form.get('user_id', type=int)
            tab = request.form.get('return_tab', 'students')
            if uid:
                with get_db() as conn:
                    delete_user(conn, uid)
                flash('Пользователь удалён.')
            return redirect(url_for('admin_panel', tab=tab))
        if action == 'create_teacher':
            return _admin_create_teacher()
        if action == 'update_teacher':
            return _admin_update_teacher()
        if action == 'delete_teacher':
            uid = request.form.get('user_id', type=int)
            if uid:
                with get_db() as conn:
                    delete_user(conn, uid)
                flash('Преподаватель удалён.')
            return redirect(url_for('admin_panel', tab='teachers'))
        if action == 'create_guard':
            return _admin_create_guard()
        if action == 'update_guard':
            return _admin_update_guard()

    group_id = request.args.get('group_id', type=int)
    search_q = request.args.get('q', '').strip()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 50
    offset = (page - 1) * per_page

    with get_db() as conn:
        students_total = count_students_admin(conn, group_id, search_q or None)
        students = list_students_admin(
            conn, group_id, search_q or None, limit=per_page, offset=offset,
        )
        teachers = list_teachers_admin(conn)
        guards = list_guards_admin(conn)
        schedule_teachers = list_schedule_teacher_names(conn)
        all_groups = list_groups(conn)
        vyatsu_links = {
            r['teacher_user_id']: r for r in list_vyatsu_link_statuses(conn)
        }

    total_pages = max(1, (students_total + per_page - 1) // per_page)

    return render_template(
        'admin_panel.html',
        tab=tab,
        students=students,
        students_total=students_total,
        students_page=page,
        students_total_pages=total_pages,
        filter_group_id=group_id,
        filter_q=search_q,
        teachers=teachers,
        guards=guards,
        schedule_teachers=schedule_teachers,
        all_groups=all_groups,
        parser_output=parser_output,
        uploaded_filename=uploaded_filename,
        vyatsu_links=vyatsu_links,
    )


def _admin_create_student():
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
    pass_number = request.form.get('pass_number', '').strip()[:64]
    face_photo = request.files.get('face_photo')

    if not all([email, password, group_name, last_name, first_name, card_number, study_form, issue_date, course_number]):
        flash('Заполните обязательные поля.')
        return redirect(url_for('admin_panel', tab='students'))
    if not is_password_allowed(password) or not is_card_number_valid(card_number):
        flash('Проверьте пароль и номер билета.')
        return redirect(url_for('admin_panel', tab='students'))

    course = get_course_from_group(group_name)
    student_id = f"STU-{email.split('@')[0][:5]}-{course}"
    try:
        issue_date = datetime.strptime(issue_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Некорректная дата.')
        return redirect(url_for('admin_panel', tab='students'))

    with get_db() as conn:
        if email_exists(conn, email):
            flash('Email уже занят.')
            return redirect(url_for('admin_panel', tab='students'))
        group_id = get_or_create_group(conn, group_name)
        user_id = create_student_user(
            conn, email, hash_password(password), last_name, first_name, middle_name or None,
            group_id, student_id, course,
            {
                'card_number_hash': hash_card_number(card_number),
                'card_number_last4': card_number[-4:],
                'study_form': study_form,
                'issue_date': issue_date,
                'course_number': int(course_number),
                'face_photo_path': None,
            },
        )
        path, err = save_private_student_photo(face_photo, user_id, 'face')
        if err:
            flash(err)
            return redirect(url_for('admin_panel', tab='students'))
        if path:
            conn.execute(
                'UPDATE student_profiles SET face_photo_path = %s WHERE user_id = %s',
                (path, user_id),
            )
        update_student_pass_number(conn, user_id, pass_number or None)
    flash('Студент создан.')
    return redirect(url_for('admin_panel', tab='students'))


def _admin_update_student():
    user_id = request.form.get('user_id', type=int)
    email = request.form.get('email', '').strip()
    group_name = request.form.get('group_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    card_number = request.form.get('card_number', '').strip()
    study_form = request.form.get('study_form', '').strip()
    issue_date = request.form.get('issue_date', '').strip()
    course_number = request.form.get('course_number', '').strip()
    pass_number = request.form.get('pass_number', '').strip()[:64]
    face_photo = request.files.get('face_photo')

    if not user_id:
        flash('Некорректный ID.')
        return redirect(url_for('admin_panel', tab='students'))

    course = get_course_from_group(group_name)
    student_id = f"STU-{email.split('@')[0][:5]}-{course}"
    try:
        issue_date = datetime.strptime(issue_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Некорректная дата.')
        return redirect(url_for('admin_panel', tab='students'))

    with get_db() as conn:
        if email_exists(conn, email, user_id):
            flash('Email занят.')
            return redirect(url_for('admin_panel', tab='students'))
        prof = get_student_profile(conn, user_id)
        card_fields = {
            'card_number_hash': prof['card_number_hash'],
            'card_number_last4': prof['card_number_last4'],
            'study_form': study_form,
            'issue_date': issue_date,
            'course_number': int(course_number),
        }
        if card_number and is_card_number_valid(card_number):
            card_fields['card_number_hash'] = hash_card_number(card_number)
            card_fields['card_number_last4'] = card_number[-4:]
        path, err = save_private_student_photo(face_photo, user_id, 'face')
        if err:
            flash(err)
            return redirect(url_for('admin_panel', tab='students'))
        if path:
            card_fields['face_photo_path'] = path
        group_id = get_or_create_group(conn, group_name)
        update_student(
            conn, user_id, email, last_name, first_name, middle_name or None,
            group_id, student_id, course, card_fields,
        )
        update_student_pass_number(conn, user_id, pass_number or None)
    flash('Студент обновлён.')
    return redirect(url_for('admin_panel', tab='students'))


def _admin_create_teacher():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    position = request.form.get('position_title', '').strip()
    office = request.form.get('office_room', '').strip()
    st_id = request.form.get('schedule_teacher_id', type=int)

    if not all([email, password, last_name, first_name, office]):
        flash('Заполните обязательные поля преподавателя.')
        return redirect(url_for('admin_panel', tab='teachers'))
    if not is_password_allowed(password) or not validate_office_room(office):
        flash('Проверьте пароль и кабинет (формат 5-104).')
        return redirect(url_for('admin_panel', tab='teachers'))

    with get_db() as conn:
        if email_exists(conn, email):
            flash('Email занят.')
            return redirect(url_for('admin_panel', tab='teachers'))
        create_teacher_user(
            conn, email, hash_password(password), last_name, first_name,
            middle_name or None, position, office, st_id,
            request.form.get('pass_number', '').strip() or None,
            request.form.get('department', '').strip() or None,
        )
    flash('Преподаватель создан.')
    return redirect(url_for('admin_panel', tab='teachers'))


def _admin_update_teacher():
    user_id = request.form.get('user_id', type=int)
    email = request.form.get('email', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    position = request.form.get('position_title', '').strip()
    office = request.form.get('office_room', '').strip()
    st_id = request.form.get('schedule_teacher_id', type=int) or None

    if not user_id or not validate_office_room(office):
        flash('Проверьте данные.')
        return redirect(url_for('admin_panel', tab='teachers'))

    with get_db() as conn:
        if email_exists(conn, email, user_id):
            flash('Email занят.')
            return redirect(url_for('admin_panel', tab='teachers'))
        update_teacher(
            conn, user_id, email, last_name, first_name, middle_name or None,
            position, office, st_id,
            request.form.get('pass_number', '').strip() or None,
            request.form.get('department', '').strip() or None,
        )
    flash('Преподаватель обновлён.')
    return redirect(url_for('admin_panel', tab='teachers'))


def _admin_create_guard():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    if not all([email, password, last_name, first_name]):
        flash('Заполните email, пароль и ФИО охранника.')
        return redirect(url_for('admin_panel', tab='guards'))
    if not is_password_allowed(password):
        flash('Пароль: только латиница и цифры.')
        return redirect(url_for('admin_panel', tab='guards'))
    with get_db() as conn:
        if email_exists(conn, email):
            flash('Email уже занят.')
            return redirect(url_for('admin_panel', tab='guards'))
        create_guard_user(
            conn, email, hash_password(password),
            last_name, first_name, middle_name or None,
        )
    flash('Сотрудник охраны создан.')
    return redirect(url_for('admin_panel', tab='guards'))


def _admin_update_guard():
    user_id = request.form.get('user_id', type=int)
    email = request.form.get('email', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    if not user_id or not all([email, last_name, first_name]):
        flash('Заполните email и ФИО.')
        return redirect(url_for('admin_panel', tab='guards'))
    with get_db() as conn:
        existing = conn.execute(
            'SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id AND r.code = %s WHERE u.id = %s',
            ('guard', user_id),
        ).fetchone()
        if not existing:
            flash('Сотрудник охраны не найден.')
            return redirect(url_for('admin_panel', tab='guards'))
        if email_exists(conn, email, exclude_user_id=user_id):
            flash('Email уже занят.')
            return redirect(url_for('admin_panel', tab='guards'))
        update_guard_user(conn, user_id, email, last_name, first_name, middle_name or None)
    flash('Данные сотрудника охраны сохранены.')
    return redirect(url_for('admin_panel', tab='guards'))


@app.route('/appointment/cancel/<int:booking_id>', methods=['POST'])
@login_required
@role_required('student')
def appointment_cancel(booking_id):
    with get_db() as conn:
        ok, err = cancel_student_booking(conn, booking_id, session['user_id'])
        if ok:
            flash('Запись отменена.')
        else:
            flash(err or 'Не удалось отменить', 'warning')
    return redirect(request.referrer or url_for('appointment_mine'))


@app.route('/gate/<token>')
def gate_entry(token):
    return render_template('gate_entry.html', token=token)


@app.route('/guard')
@login_required
@role_required('guard')
def guard_scan():
    return render_template('guard/scan.html')


@app.route('/api/guard/verify', methods=['POST'])
@login_required
@role_required('guard')
def api_guard_verify():
    data = request.get_json(silent=True) or {}
    token_str = (data.get('token') or '').strip()
    if not token_str:
        return jsonify({'ok': False, 'error': 'Токен не указан'}), 400
    with get_db() as conn:
        row = get_valid_token(conn, token_str)
        if not row or not row.get('is_active'):
            return jsonify({'ok': False, 'error': 'Токен недействителен или истёк'}), 404
        subject = row['subject_type']
        fio = format_fio(row=row)
        photo_url = None
        pass_number = None
        department = None
        position_title = None
        group_name = None
        student_id = None
        course_number = None
        study_form = None
        issue_date = None
        card_number_masked = None
        if subject == 'student':
            prof = get_student_profile(conn, row['user_id'])
            if prof:
                group_name = prof.get('group_name')
                student_id = prof.get('student_id')
                course_number = prof.get('course_number')
                study_form = prof.get('study_form')
                issue_date = prof.get('issue_date')
                pass_number = prof.get('pass_number')
                if prof.get('card_number_last4'):
                    card_number_masked = f'****{prof["card_number_last4"]}'
                if not pass_number and card_number_masked:
                    pass_number = card_number_masked
                if prof.get('face_photo_path'):
                    photo_url = url_for('student_card_face_photo', user_id=row['user_id'])
        else:
            prof = get_teacher_profile(conn, row['user_id'])
            if prof:
                pass_number = prof.get('pass_number')
                department = prof.get('department')
                position_title = prof.get('position_title')
        exp = row['expires_at']
        valid_until = exp.isoformat() if hasattr(exp, 'isoformat') else str(exp)
        initials = format_fio(row=row)
        photo_initials = ''.join(w[0] for w in initials.split()[:2]).upper() if initials else '?'
    return jsonify({
        'ok': True,
        'subject_type': subject,
        'fio': fio,
        'photo_url': photo_url,
        'photo_initials': photo_initials,
        'pass_number': pass_number,
        'department': department,
        'position_title': position_title,
        'group': group_name,
        'student_id': student_id,
        'course_number': course_number,
        'study_form': study_form,
        'issue_date': str(issue_date) if issue_date else None,
        'card_number_masked': card_number_masked,
        'valid_until': valid_until,
    })


@app.route('/api/my-qr-token')
@login_required
def api_my_qr_token():
    role = session.get('role')
    if role == 'student':
        subject = 'student'
    elif role == 'teacher':
        subject = 'teacher'
    else:
        return jsonify({'error': 'Недоступно'}), 403
    qr_url, token, expires = _refresh_user_qr(session['user_id'], subject)
    return jsonify({
        'ok': True,
        'qr_url': qr_url,
        'token': token,
        'expires_at': expires.isoformat() if hasattr(expires, 'isoformat') else str(expires),
    })


@app.route('/api/slots/<int:slot_id>/queue', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_slot_queue(slot_id):
    with get_db() as conn:
        if request.method == 'GET':
            rows = list_queue(conn, slot_id)
            return jsonify({
                'ok': True,
                'queue': [
                    {
                        'position': r['position'],
                        'fio': format_display_name(row=r),
                        'group': r.get('group_name'),
                        'student_user_id': r['student_user_id'],
                    }
                    for r in rows
                ],
            })
        if request.method == 'POST':
            from services.lesson_now import can_join_queue_now
            ok, err = can_join_queue_now(conn, slot_id, session['user_id'])
            if not ok:
                return jsonify({'error': err}), 400
            ok, err = join_queue(conn, slot_id, session['user_id'])
            if not ok:
                return jsonify({'error': err}), 400
            notify_teacher_queue_join(conn, slot_id, session['user_id'])
            return jsonify({'ok': True, 'message': 'Вы в очереди'})
        ok, err = leave_queue(conn, slot_id, session['user_id'])
        if not ok:
            return jsonify({'error': err}), 400
        return jsonify({'ok': True})


@app.route('/api/slots/<int:slot_id>/queue/<int:entry_id>', methods=['PATCH'])
@login_required
@role_required('teacher')
def api_slot_queue_passed(slot_id, entry_id):
    data = request.get_json(silent=True) or {}
    passed = data.get('passed') in (True, 'true', '1', 1, 'on')
    with get_db() as conn:
        ok, err = set_queue_passed(conn, entry_id, slot_id, session['user_id'], passed)
    if not ok:
        return jsonify({'error': err or 'Не найдено'}), 404
    return jsonify({'ok': True, 'passed': passed})


@app.route('/api/slots/<int:slot_id>/submissions', methods=['GET', 'POST'])
@login_required
def api_slot_submissions(slot_id):
    with get_db() as conn:
        if request.method == 'GET':
            uid = None if session.get('role') == 'teacher' else session['user_id']
            rows = list_submissions(conn, slot_id, uid)
            return jsonify({
                'ok': True,
                'submissions': [
                    {
                        'id': r['id'],
                        'name': r['original_name'],
                        'fio': format_fio(
                            r.get('last_name'), r.get('first_name'), r.get('middle_name'),
                        ),
                        'group': r.get('group_name'),
                        'url': url_for('api_slot_submission_download', submission_id=r['id']),
                        'student_user_id': r['student_user_id'],
                    }
                    for r in rows
                ],
            })
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'error': 'Файл не выбран'}), 400
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ALLOWED_CALENDAR_EXTENSIONS:
            return jsonify({'error': 'Тип файла не разрешён'}), 400
        safe = secure_filename(file.filename)
        stored = f'{session["user_id"]}_{datetime.now().strftime("%Y%m%d%H%M%S")}_{safe}'
        path = os.path.join(SLOT_SUBMISSIONS_DIR, stored)
        file.save(path)
        sid, err = add_submission(conn, slot_id, session['user_id'], path, file.filename)
        if err:
            return jsonify({'error': err}), 400
        return jsonify({
            'ok': True,
            'id': sid,
            'message': 'Работа загружена',
            'url': url_for('api_slot_submission_download', submission_id=sid),
        })


@app.route('/api/slots/submissions/<int:submission_id>', methods=['DELETE'])
@login_required
def api_slot_submission_delete(submission_id):
    with get_db() as conn:
        path, err = delete_submission(conn, submission_id, session['user_id'])
    if err:
        return jsonify({'error': err}), 404
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return jsonify({'ok': True, 'message': 'Файл удалён'})


@app.route('/api/slots/submissions/<int:submission_id>/download')
@login_required
def api_slot_submission_download(submission_id):
    with get_db() as conn:
        row = get_submission(conn, submission_id)
        if not row:
            abort(404)
        if session.get('role') != 'teacher' and row['student_user_id'] != session['user_id']:
            abort(403)
    if not os.path.isfile(row['stored_path']):
        abort(404)
    return send_file(row['stored_path'], as_attachment=True, download_name=row['original_name'])


@app.route('/api/calendar/event-meta')
@login_required
def api_calendar_event_meta():
    event_key = request.args.get('event_key', '').strip()
    if not event_key:
        return jsonify({'error': 'event_key required'}), 400
    with get_db() as conn:
        note = get_note(conn, session['user_id'], event_key)
        slot_id = resolve_slot_id_from_event_key(conn, event_key)
        keys = attachment_event_keys_for_lookup(event_key, slot_id)
        attachments = list_attachments_for_event_keys(conn, keys)
        my_files = list_note_files_for_event(conn, session['user_id'], event_key)
        bookings = []
        queue = []
        submissions = []
        slot_flags = {}
        in_queue = False
        can_join_queue = False
        if slot_id:
            slot_row = conn.execute(
                'SELECT enable_queue, enable_submission FROM office_slots WHERE id = %s',
                (slot_id,),
        ).fetchone()
            if slot_row:
                slot_flags = {
                    'enable_queue': bool(slot_row.get('enable_queue')),
                    'enable_submission': bool(slot_row.get('enable_submission')),
                }
            if session.get('role') == 'teacher':
                bookings = [
                    {
                        'id': b['id'],
                        'status': b['status'],
                        'fio': format_fio(
                            b.get('last_name'), b.get('first_name'), b.get('middle_name'),
                        ),
                        'group': b.get('group_name'),
                    }
                    for b in list_slot_bookings(conn, slot_id)
                ]
                queue = [
                    {
                        'id': q['id'],
                        'position': q['position'],
                        'fio': format_display_name(row=q),
                        'group': q.get('group_name'),
                        'passed': q.get('passed_at') is not None,
                    }
                    for q in list_queue(conn, slot_id)
                ]
                submissions = [
                    {
                        'id': s['id'],
                        'name': s['original_name'],
                        'fio': format_fio(
                            s.get('last_name'), s.get('first_name'), s.get('middle_name'),
                        ),
                        'group': s.get('group_name'),
                        'url': url_for('api_slot_submission_download', submission_id=s['id']),
                    }
                    for s in list_submissions(conn, slot_id)
                ]
            elif slot_flags.get('enable_queue'):
                in_queue = get_queue_entry(conn, slot_id, session['user_id']) is not None
            if slot_flags.get('enable_submission') and session.get('role') == 'student':
                submissions = [
                    {
                        'id': s['id'],
                        'name': s['original_name'],
                        'url': url_for('api_slot_submission_download', submission_id=s['id']),
                    }
                    for s in list_submissions(conn, slot_id, session['user_id'])
                ]
            if slot_flags.get('enable_queue') and session.get('role') == 'student':
                from services.lesson_now import can_join_queue_now
                ok, _ = can_join_queue_now(conn, slot_id, session['user_id'])
                can_join_queue = ok
    return jsonify({
        'event_key': event_key,
        'note': note['note_text'] if note else '',
        'teacher_files': _serialize_teacher_files(attachments),
        'my_files': [
            {
                'id': f['id'],
                'name': f['original_name'],
                'url': url_for('api_calendar_note_file_download', file_id=f['id']),
            }
            for f in my_files
        ],
        'attachments': _serialize_teacher_files(attachments),
        'role': session.get('role'),
        'bookings': bookings,
        'queue': queue,
        'submissions': submissions,
        'slot_flags': slot_flags,
        'in_queue': in_queue,
        'can_join_queue': can_join_queue,
    })


@app.route('/api/calendar/notes', methods=['PUT', 'DELETE'])
@login_required
def api_calendar_notes():
    if request.method == 'DELETE':
        event_key = (request.args.get('event_key') or '').strip()
        if not event_key:
            return jsonify({'error': 'event_key required'}), 400
        with get_db() as conn:
            delete_note(conn, session['user_id'], event_key)
        return jsonify({'ok': True, 'message': 'Заметка удалена'})

    data = request.get_json(silent=True) or {}
    event_key = (data.get('event_key') or '').strip()
    if not event_key:
        return jsonify({'error': 'event_key required'}), 400
    with get_db() as conn:
        upsert_note(
            conn, session['user_id'], event_key,
            data.get('event_type', 'lesson'), data.get('note_text', ''),
        )
    return jsonify({'ok': True, 'message': 'Заметка сохранена'})


@app.route('/api/calendar/attachments', methods=['POST'])
@login_required
@role_required('teacher')
def api_calendar_attachments_upload():
    event_key = (request.form.get('event_key') or '').strip()
    event_type = request.form.get('event_type', 'lesson')
    slot_id = request.form.get('slot_id', type=int)
    if slot_id and not event_key.startswith('slot:'):
        event_key = f'slot:{slot_id}'
        event_type = 'office_slot'
    if not event_key:
        return jsonify({'error': 'event_key required'}), 400
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'Файл не выбран'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_CALENDAR_EXTENSIONS:
        return jsonify({'error': 'Тип файла не разрешён'}), 400
    with get_db() as conn:
        if not teacher_can_attach_to_event(
            conn, session['user_id'], event_key, event_type, slot_id,
        ):
            return jsonify({'error': 'Можно прикреплять файлы только к своим парам или слотам'}), 403
    safe = secure_filename(file.filename)
    stored = f'{session["user_id"]}_{datetime.now().strftime("%Y%m%d%H%M%S")}_{safe}'
    path = os.path.join(CALENDAR_ATTACHMENTS_DIR, stored)
    file.save(path)
    with get_db() as conn:
        aid = insert_attachment(
            conn, session['user_id'], event_key,
            event_type, path, file.filename,
        )
        if slot_id or event_type == 'office_slot':
            sid = slot_id
            if not sid and event_key.startswith('slot:'):
                try:
                    sid = int(event_key.split(':', 1)[1])
                except ValueError:
                    sid = None
            if sid:
                notify_students_slot_material(conn, sid)
    return jsonify({
        'ok': True,
        'message': 'Файл добавлен',
        'id': aid,
        'url': url_for('api_calendar_attachment_download', attachment_id=aid),
        'name': file.filename,
    })


@app.route('/api/calendar/attachments/<int:attachment_id>')
@login_required
def api_calendar_attachment_download(attachment_id):
    with get_db() as conn:
        row = get_attachment(conn, attachment_id)
        if not row or not user_can_download_attachment(
            conn, session['user_id'], session.get('role'), row,
        ):
            abort(403)
    if not os.path.isfile(row['stored_path']):
        abort(404)
    return send_file(
        row['stored_path'],
        as_attachment=True,
        download_name=row['original_name'],
    )


@app.route('/api/calendar/note-files', methods=['POST'])
@login_required
def api_calendar_note_files_upload():
    event_key = (request.form.get('event_key') or '').strip()
    if not event_key:
        return jsonify({'error': 'event_key required'}), 400
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'Файл не выбран'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_CALENDAR_EXTENSIONS:
        return jsonify({'error': 'Тип файла не разрешён'}), 400
    safe = secure_filename(file.filename)
    stored = f'{session["user_id"]}_{datetime.now().strftime("%Y%m%d%H%M%S")}_{safe}'
    path = os.path.join(CALENDAR_NOTE_FILES_DIR, stored)
    file.save(path)
    with get_db() as conn:
        fid = insert_note_file(
            conn, session['user_id'], event_key,
            request.form.get('event_type', 'lesson'), path, file.filename,
        )
    return jsonify({
        'ok': True,
        'message': 'Файл добавлен',
        'id': fid,
        'url': url_for('api_calendar_note_file_download', file_id=fid),
        'name': file.filename,
    })


@app.route('/api/calendar/note-files/<int:file_id>', methods=['GET', 'DELETE'])
@login_required
def api_calendar_note_file_download(file_id):
    if request.method == 'DELETE':
        with get_db() as conn:
            ok = delete_note_file(conn, session['user_id'], file_id)
        if not ok:
            return jsonify({'error': 'Не найдено'}), 404
        return jsonify({'ok': True, 'message': 'Файл удалён'})

    with get_db() as conn:
        row = get_note_file(conn, file_id)
    if not row or row['user_id'] != session['user_id']:
        abort(403)
    if not os.path.isfile(row['stored_path']):
        abort(404)
    return send_file(
        row['stored_path'],
        as_attachment=True,
        download_name=row['original_name'],
    )


@app.route('/api/teacher/slots/<int:slot_id>', methods=['PATCH', 'DELETE'])
@login_required
@role_required('teacher')
def api_teacher_slot_detail(slot_id):
    if request.method == 'DELETE':
        try:
            with get_db() as conn:
                ok = delete_office_slot(conn, slot_id, session['user_id'])
            if not ok:
                return jsonify({'error': 'Не найдено'}), 404
            return jsonify({'ok': True})
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 409

    data = request.get_json(silent=True) or {}
    try:
        with get_db() as conn:
            sd = data.get('slot_date')
            conflict_events, _, _ = _build_teacher_calendar_events(
                conn, session['user_id'], sd, sd,
            )
            confirm_overlap = data.get('confirm_overlap') in (
                True, 'true', '1', 1, 'yes',
            )
            update_office_slot(
                conn, slot_id, session['user_id'], data,
                conflict_events=conflict_events,
                confirm_overlap=confirm_overlap,
            )
        return jsonify({'ok': True})
    except ValueError as exc:
        err = str(exc)
        if err == 'LESSON_OVERLAP':
            return jsonify({'error': 'В это время пара.', 'need_confirm': True}), 409
        return jsonify({'error': err}), 409


@app.route('/admin/sync-campus', methods=['POST'])
@login_required
@role_required('admin')
def admin_sync_campus():
    try:
        from parsers.vyatsu_campus import main as sync_campus
        sync_campus()
        flash('Корпуса и общежития обновлены.')
    except Exception as exc:
        flash(f'Ошибка синхронизации: {exc}')
    return redirect(url_for('admin_panel', tab='schedule'))


@app.route('/news')
def news():
    news_items, parse_error = get_news_for_site(10)
    return render_template(
        'news.html', news=news_items, source_url=VK_GROUP_URL, parse_error=parse_error,
    )


@app.route('/map')
def map():
    highlighted = normalize_building_number(request.args.get('building', ''))
    building_detail = None
    dorms = []
    buildings = []
    try:
        with get_db() as conn:
            dorms = [dict(r) for r in list_buildings(conn, 'dorm')]
            buildings = [dict(r) for r in list_buildings(conn, 'building')]
            if highlighted:
                building_detail = get_building_by_number(conn, int(highlighted), 'building')
                if building_detail:
                    building_detail = dict(building_detail)
    except Exception:
        pass
    return render_template(
        'map.html',
        dorms=dorms,
        buildings=buildings,
        map_locations=dorms + buildings,
        dorms_source_url=VYATSU_DORMS_URL,
        buildings_source_url=VYATSU_BUILDINGS_URL,
        highlighted_building=highlighted,
    )


@app.route('/faq')
def faq():
    with get_db() as conn:
        faqs = list_faq(conn)
    return render_template('faq.html', faqs=faqs)


@app.route('/student_card')
@login_required
@role_required('student')
def student_card():
    return redirect(url_for('dashboard'))


@app.route('/student_card/face/<int:user_id>')
def student_card_face_photo(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    is_owner = session.get('user_id') == user_id
    role = session.get('role')
    if not is_owner and role not in ('admin', 'guard'):
        abort(403)
    with get_db() as conn:
        prof = get_student_profile(conn, user_id)
    path = prof.get('face_photo_path') if prof else None
    if not path:
        abort(404)
    abs_path = os.path.join(PRIVATE_STORAGE_DIR, path)
    if not os.path.exists(abs_path):
        abort(404)
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'image/jpeg', max_age=0)


@app.route('/api/notifications')
@login_required
def api_notifications_list():
    with get_db() as conn:
        rows = list_notifications(conn, session['user_id'], limit=40)
        unread = count_unread_notifications(conn, session['user_id'])
    return jsonify({
        'ok': True,
        'unread': unread,
        'items': [
            {
                'id': r['id'],
                'kind': r['kind'],
                'title': r['title'],
                'body': r['body'],
                'url': r.get('link_url'),
                'is_read': bool(r.get('is_read')),
                'created_at': r['created_at'].isoformat()
                if hasattr(r.get('created_at'), 'isoformat') else str(r.get('created_at')),
            }
            for r in rows
        ],
    })


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def api_notification_read(notification_id):
    with get_db() as conn:
        ok = mark_notification_read(conn, notification_id, session['user_id'])
    if not ok:
        return jsonify({'error': 'Не найдено'}), 404
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_notifications_read_all():
    with get_db() as conn:
        mark_all_notifications_read(conn, session['user_id'])
    return jsonify({'ok': True})


@app.route('/api/push/vapid-key')
@login_required
def api_push_vapid_key():
    return jsonify({
        'ok': True,
        'publicKey': get_vapid_public_key(),
        'enabled': push_enabled(),
    })


@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get('endpoint') or '').strip()
    keys = data.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Неверные данные подписки'}), 400
    with get_db() as conn:
        upsert_push_subscription(conn, session['user_id'], endpoint, p256dh, auth)
    return jsonify({'ok': True})


@app.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def api_push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get('endpoint') or '').strip()
    if endpoint:
        with get_db() as conn:
            delete_push_subscription(conn, session['user_id'], endpoint)
    return jsonify({'ok': True})


@app.route('/manifest.webmanifest')
def pwa_manifest():
    return send_from_directory(
        app.static_folder, 'manifest.webmanifest',
        mimetype='application/manifest+json', max_age=3600,
    )


@app.route('/sw.js')
def pwa_service_worker():
    resp = send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    return resp


def _news_refresh_loop():
    time.sleep(8)
    while True:
        try:
            refresh_vk_news_cache()
        except Exception:
            pass
        time.sleep(int(os.getenv('VK_NEWS_TTL_SECONDS', '3600')))


threading.Thread(target=_news_refresh_loop, daemon=True).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug)
