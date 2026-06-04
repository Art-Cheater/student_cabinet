"""Navigation helpers for calendar views (week / day / month)."""
from datetime import date, timedelta

MONTHS_RU = (
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
)

WEEKDAYS_RU_SHORT = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')


def day_label_for(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    wd = WEEKDAYS_RU_SHORT[d.weekday()]
    return f'{d.day} {MONTHS_RU[d.month - 1].lower()} {d.year}, {wd}'


def week_start_on(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d - timedelta(days=d.weekday())


def month_label_for(d):
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f'{MONTHS_RU[d.month - 1]} {d.year}'


def build_calendar_nav(view=None, week=None, day=None, month=None):
    """Return dict for templates: view, dates, labels, prev/next links params."""
    view = view or 'week'
    today = date.today()

    if view == 'month':
        if month:
            parts = month.split('-')
            y, m = int(parts[0]), int(parts[1])
        else:
            y, m = today.year, today.month
        first = date(y, m, 1)
        if m == 12:
            next_first = date(y + 1, 1, 1)
        else:
            next_first = date(y, m + 1, 1)
        prev_m = m - 1 if m > 1 else 12
        prev_y = y if m > 1 else y - 1
        return {
            'today': today.isoformat(),
            'view': 'month',
            'month': f'{y:04d}-{m:02d}',
            'month_label': month_label_for(first),
            'week_start': week_start_on(first).isoformat(),
            'day': today.isoformat(),
            'prev_month': f'{prev_y:04d}-{prev_m:02d}',
            'next_month': f'{next_first.year:04d}-{next_first.month:02d}',
            'prev_week': None,
            'next_week': None,
            'prev_day': None,
            'next_day': None,
        }

    if view == 'day':
        active = today
        if day:
            try:
                active = date.fromisoformat(day[:10])
            except ValueError:
                pass
        ws = week_start_on(active)
        return {
            'today': today.isoformat(),
            'view': 'day',
            'day': active.isoformat(),
            'day_label': day_label_for(active),
            'week_start': ws.isoformat(),
            'month': f'{active.year:04d}-{active.month:02d}',
            'month_label': month_label_for(active),
            'prev_day': (active - timedelta(days=1)).isoformat(),
            'next_day': (active + timedelta(days=1)).isoformat(),
            'prev_week': (ws - timedelta(days=7)).isoformat(),
            'next_week': (ws + timedelta(days=7)).isoformat(),
            'prev_month': None,
            'next_month': None,
        }

    # week (default)
    ws = week_start_on(today)
    if week:
        try:
            ws = week_start_on(date.fromisoformat(week[:10]))
        except ValueError:
            pass
    return {
        'today': today.isoformat(),
        'view': 'week',
        'week_start': ws.isoformat(),
        'day': today.isoformat(),
        'month': f'{ws.year:04d}-{ws.month:02d}',
        'month_label': month_label_for(ws),
        'prev_week': (ws - timedelta(days=7)).isoformat(),
        'next_week': (ws + timedelta(days=7)).isoformat(),
        'prev_day': (today - timedelta(days=1)).isoformat(),
        'next_day': (today + timedelta(days=1)).isoformat(),
        'prev_month': None,
        'next_month': None,
    }


def date_range_for_nav(nav, extra_days=0):
    """Return (date_from, date_to) inclusive for loading events."""
    """Inclusive date range for loading events."""
    view = nav['view']
    if view == 'month':
        y, m = map(int, nav['month'].split('-'))
        first = date(y, m, 1)
        if m == 12:
            last = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)
        return first, last
    if view == 'day':
        d = date.fromisoformat(nav['day'])
        return d, d
    ws = date.fromisoformat(nav['week_start'])
    return ws, ws + timedelta(days=6 + extra_days)
