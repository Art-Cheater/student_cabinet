"""In-app and Web Push notifications."""
import json
import os
import threading

from db.connection import get_db
from db.queries.notifications import (
    create_notification, list_push_subscriptions, delete_push_subscription,
)
from utils import format_fio

_push_lock = threading.Lock()


def _vapid_claims():
    sub = os.getenv('VAPID_SUBJECT', 'mailto:admin@vyatsu.ru')
    return {'sub': sub}


def push_enabled():
    return bool(os.getenv('VAPID_PRIVATE_KEY') and os.getenv('VAPID_PUBLIC_KEY'))


def get_vapid_public_key():
    return os.getenv('VAPID_PUBLIC_KEY', '')


def notify_user(user_id, kind, title, body, link_url=None):
    """Create in-app notification and send push to subscribed devices."""
    with get_db() as conn:
        nid = create_notification(conn, user_id, kind, title, body, link_url)
        subs = list_push_subscriptions(conn, user_id)
    if subs and push_enabled():
        payload = json.dumps({
            'title': title,
            'body': body,
            'url': link_url or '/',
            'id': nid,
        }, ensure_ascii=False)
        for sub in subs:
            _send_push_async(user_id, sub, payload)
    return nid


def _send_push_async(user_id, subscription, payload):
    def _run():
        try:
            from pywebpush import webpush
            webpush(
                subscription_info={
                    'endpoint': subscription['endpoint'],
                    'keys': {
                        'p256dh': subscription['p256dh'],
                        'auth': subscription['auth'],
                    },
                },
                data=payload,
                vapid_private_key=os.getenv('VAPID_PRIVATE_KEY'),
                vapid_claims=_vapid_claims(),
            )
        except Exception as exc:
            code = getattr(exc, 'response', None)
            status = getattr(code, 'status_code', None) if code else None
            if status in (404, 410):
                with get_db() as conn:
                    delete_push_subscription(conn, user_id, subscription['endpoint'])

    threading.Thread(target=_run, daemon=True).start()


def notify_teacher_queue_join(conn, slot_id, student_user_id):
    slot = conn.execute('''
        SELECT os.topic, os.teacher_user_id,
               u.last_name, u.first_name, u.middle_name
        FROM office_slots os
        JOIN users u ON u.id = %s
        WHERE os.id = %s
    ''', (student_user_id, slot_id)).fetchone()
    if not slot:
        return
    fio = format_fio(
        slot.get('last_name'), slot.get('first_name'), slot.get('middle_name'),
    )
    notify_user(
        slot['teacher_user_id'],
        'queue_join',
        'Новая запись в очередь',
        f'{fio} встал(а) в очередь: {slot["topic"]}',
        f'/teacher/schedule',
    )


def notify_teacher_booking(conn, slot_id, student_user_id):
    row = conn.execute('''
        SELECT os.topic, os.teacher_user_id,
               u.last_name, u.first_name, u.middle_name
        FROM office_slots os
        JOIN users u ON u.id = %s
        WHERE os.id = %s
    ''', (student_user_id, slot_id)).fetchone()
    if not row:
        return
    fio = format_fio(row.get('last_name'), row.get('first_name'), row.get('middle_name'))
    notify_user(
        row['teacher_user_id'],
        'booking_created',
        'Новая запись к преподавателю',
        f'{fio} записался(ась): {row["topic"]}',
        '/teacher/slots',
    )


def notify_student_booking_rejected(conn, booking_id):
    row = conn.execute('''
        SELECT ob.student_user_id, os.topic,
               t.last_name, t.first_name, t.middle_name
        FROM office_bookings ob
        JOIN office_slots os ON os.id = ob.slot_id
        JOIN users t ON t.id = os.teacher_user_id
        WHERE ob.id = %s
    ''', (booking_id,)).fetchone()
    if not row:
        return
    teacher = format_fio(row.get('last_name'), row.get('first_name'), row.get('middle_name'))
    notify_user(
        row['student_user_id'],
        'booking_rejected',
        'Запись отменена',
        f'Преподаватель {teacher} отклонил(а) запись: {row["topic"]}',
        '/appointment/mine',
    )


def notify_students_slot_material(conn, slot_id, title='Новые материалы'):
    slot = conn.execute('''
        SELECT os.topic, os.audience_type, os.teacher_user_id,
               t.last_name, t.first_name, t.middle_name
        FROM office_slots os
        JOIN users t ON t.id = os.teacher_user_id
        WHERE os.id = %s
    ''', (slot_id,)).fetchone()
    if not slot:
        return
    teacher = format_fio(slot.get('last_name'), slot.get('first_name'), slot.get('middle_name'))
    body = f'{teacher} выложил(а) материалы: {slot["topic"]}'
    if slot['audience_type'] == 'anyone':
        students = conn.execute('''
            SELECT u.id FROM users u
            JOIN roles r ON r.id = u.role_id AND r.code = 'student'
            WHERE u.is_active = TRUE
        ''').fetchall()
    else:
        students = conn.execute('''
            SELECT DISTINCT sp.user_id AS id
            FROM office_slot_groups osg
            JOIN student_profiles sp ON sp.group_id = osg.group_id
            WHERE osg.slot_id = %s
        ''', (slot_id,)).fetchall()
    for s in students:
        notify_user(s['id'], 'teacher_material', title, body, '/dashboard')
