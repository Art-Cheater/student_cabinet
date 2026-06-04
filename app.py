import json
import os
import subprocess
import sys
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
from db.queries.settings import get_setting, mask_token, set_setting
from db.queries.external_schedule import list_vyatsu_link_statuses
from db.queries.schedule import (
    get_group_schedule, get_schedule_events, get_latest_effective_from,
    get_teacher_lesson_events, list_schedule_teacher_names,
)
from db.queries.users import (
    create_guard_user, create_student_user, create_teacher_user, delete_user, email_exists,
    get_student_profile, get_teacher_profile, get_teacher_public,
    get_user_by_email, get_user_by_id,
    count_students_admin, list_students_admin, list_teachers_admin, list_teachers_public,
    update_student, update_teacher,
)
from parsers.vyatsu_teacher_busy import get_teacher_university_events
from services.calendar_events import (
    booking_to_event, group_slots_by_date, make_event_key, slot_to_event,
)
from db.queries.calendar_meta import (
    attachment_event_keys_for_lookup,
    delete_attachment,
    get_attachment,
    get_note,
    get_note_file,
    insert_attachment,
    insert_note_file,
    list_attachments_for_event_keys,
    list_note_files_for_event,
    load_user_notes_map,
    resolve_slot_id_from_event_key,
    upsert_note,
    user_can_download_attachment,
)
from services.calendar_nav import build_calendar_nav, date_range_for_nav
from services.vk_news import VK_GROUP_URL, fetch_vk_news, load_cached_news_formatted
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
    gate_url = url_for('gate_entry', token=token, _external=True)
    return (
        'https://api.qrserver.com/v1/create-qr-code/?size=260x260&data='
        + quote_plus(gate_url)
    )


def _refresh_user_qr(user_id, subject_type):
    with get_db() as conn:
        token, expires = issue_token(conn, user_id, subject_type)
    return _qr_image_url(token), token, expires
app.secret_key = os.getenv('FLASK_SECRET_KEY') or os.getenv('SECRET_KEY') or os.urandom(32).hex()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

UPLOADS_DIR = os.path.join('schedule_parser', 'uploads')
CALENDAR_ATTACHMENTS_DIR = os.path.join('uploads', 'calendar_attachments')
CALENDAR_NOTE_FILES_DIR = os.path.join('uploads', 'calendar_note_files')
os.makedirs(CALENDAR_ATTACHMENTS_DIR, exist_ok=True)
os.makedirs(CALENDAR_NOTE_FILES_DIR, exist_ok=True)


def _event_keys_from_events(events):
    keys = []
    for ev in events:
        k = ev.get('event_key') or ev.get('id')
        if k:
            keys.append(k)
    return keys


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
    news_preview = []
    news_error = None
    today_events = []
    try:
        news_preview, news_error = fetch_vk_news(limit=2)
        if not news_preview:
            news_preview = load_cached_news_formatted(2)
    except Exception:
        news_preview = load_cached_news_formatted(2)
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
        email = request.form['email'].strip()
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
                    flash(f'Добро пожаловать, {session["user_name"]}!')
                    return redirect_after_login(user['role_code'])
        except Exception as exc:
            flash(f'Ошибка входа: {exc}')
            return render_template('login.html')
        flash('Неверный email или пароль')
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
    if request.method == 'POST' and request.form.get('action') == 'upload_photo':
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

    with get_db() as conn:
        user = get_student_profile(conn, session['user_id'])
    if not user or not user.get('card_number_hash'):
        return render_template('dashboard.html', card=None, user=session, profile=None)
    fio = format_fio(row=user)
    masked = f'****{user["card_number_last4"]}' if user.get('card_number_last4') else 'скрыт'
    qr_url, _, _ = _refresh_user_qr(user['id'], 'student')
    return render_template(
        'dashboard.html',
        card=user,
        profile=user,
        fio=fio,
        masked_number=masked,
        qr_url=qr_url,
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


@app.route('/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    with get_db() as conn:
        profile = get_teacher_profile(conn, session['user_id'])
    qr_url = None
    if profile:
        qr_url, _, _ = _refresh_user_qr(session['user_id'], 'teacher')
    return render_template(
        'teacher/dashboard.html',
        profile=dict(profile) if profile else None,
        qr_url=qr_url,
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
        ok = update_booking_status(conn, booking_id, session['user_id'], status)
    if not ok:
        return jsonify({'error': 'Не найдено'}), 404
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
        if request.method == 'POST':
            slot_id = request.form.get('slot_id', type=int)
            group_id = session.get('group_id')
            if slot_id and student_can_book_slot(conn, slot_id, group_id):
                overlap_msg = student_slot_lesson_overlap(
                    conn, session.get('group'), slot_id,
                )
                ok, err = create_booking(conn, slot_id, session['user_id'])
                if ok:
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
                flash('Запись недоступна')
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
            conn, teacher_id, session.get('group_id'),
            date.today().isoformat(),
            (date.today() + timedelta(days=120)).isoformat(),
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
    )


@app.route('/admin', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_panel():
    tab = request.args.get('tab', 'students')
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
            if uid:
                with get_db() as conn:
                    delete_user(conn, uid)
                flash('Пользователь удалён.')
            return redirect(url_for('admin_panel', tab='students'))
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
        if action == 'save_vk_token':
            token = request.form.get('vk_access_token', '').strip()
            with get_db() as conn:
                set_setting(conn, 'vk_access_token', token)
            flash('VK-токен сохранён.' if token else 'VK-токен удалён.')
            return redirect(url_for('admin_panel', tab='help'))
        if action == 'create_guard':
            return _admin_create_guard()

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
        schedule_teachers = list_schedule_teacher_names(conn)
        all_groups = list_groups(conn)
        vyatsu_links = {
            r['teacher_user_id']: r for r in list_vyatsu_link_statuses(conn)
        }

    total_pages = max(1, (students_total + per_page - 1) // per_page)

    vk_token_masked = ''
    try:
        with get_db() as conn:
            vk_token_masked = mask_token(get_setting(conn, 'vk_access_token', ''))
    except Exception:
        pass

    return render_template(
        'admin_panel.html',
        tab=tab,
        vk_token_masked=vk_token_masked,
        students=students,
        students_total=students_total,
        students_page=page,
        students_total_pages=total_pages,
        filter_group_id=group_id,
        filter_q=search_q,
        teachers=teachers,
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
    # ... validation same as before
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    card_number = request.form.get('card_number', '').strip()
    study_form = request.form.get('study_form', '').strip()
    issue_date = request.form.get('issue_date', '').strip()
    course_number = request.form.get('course_number', '').strip()
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
        return redirect(url_for('admin_panel', tab='help'))
    if not is_password_allowed(password):
        flash('Пароль: только латиница и цифры.')
        return redirect(url_for('admin_panel', tab='help'))
    with get_db() as conn:
        if email_exists(conn, email):
            flash('Email уже занят.')
            return redirect(url_for('admin_panel', tab='help'))
        create_guard_user(
            conn, email, hash_password(password),
            last_name, first_name, middle_name or None,
        )
    flash('Охранник создан.')
    return redirect(url_for('admin_panel', tab='help'))


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
                if prof.get('card_number_last4'):
                    card_number_masked = f'****{prof["card_number_last4"]}'
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
    return jsonify({
        'ok': True,
        'subject_type': subject,
        'fio': fio,
        'photo_url': photo_url,
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
    })


@app.route('/api/calendar/notes', methods=['PUT'])
@login_required
def api_calendar_notes():
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
    safe = secure_filename(file.filename)
    stored = f'{session["user_id"]}_{datetime.now().strftime("%Y%m%d%H%M%S")}_{safe}'
    path = os.path.join(CALENDAR_ATTACHMENTS_DIR, stored)
    file.save(path)
    with get_db() as conn:
        aid = insert_attachment(
            conn, session['user_id'], event_key,
            event_type, path, file.filename,
        )
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


@app.route('/api/calendar/note-files/<int:file_id>')
@login_required
def api_calendar_note_file_download(file_id):
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
    return redirect(url_for('admin_panel', tab='help'))


@app.route('/news')
def news():
    news_items, parse_error = fetch_vk_news(limit=10)
    if not news_items:
        cached = load_cached_news_formatted(10)
        if cached:
            news_items = cached
            parse_error = parse_error or 'Показан кэш. Задайте VK_ACCESS_TOKEN в .env.'
    return render_template('news.html', news=news_items, source_url=VK_GROUP_URL, parse_error=parse_error)


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
    is_admin = session.get('role') == 'admin'
    if not is_owner and not is_admin:
        abort(403)
    with get_db() as conn:
        prof = get_student_profile(conn, user_id)
    path = prof.get('face_photo_path') if prof else None
    if not path:
        abort(404)
    abs_path = os.path.join(PRIVATE_STORAGE_DIR, path)
    if not os.path.exists(abs_path):
        abort(404)
    return send_file(abs_path, mimetype='image/jpeg', max_age=0)


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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug)
