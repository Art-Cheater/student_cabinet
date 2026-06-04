# Student Cabinet (VyatSU)

Веб-приложение личного кабинета на Flask с PostgreSQL:
- единый вход для студентов, преподавателей и администратора (роли в БД);
- расписание (календарь неделя/день) из Excel;
- запись к преподавателю (слоты приёма);
- новости ВК, FAQ, карта корпусов из БД;
- цифровой студенческий билет.

## Мобильный PWA

На телефоне: «Установить приложение» (Chrome) или «На экран Домой» (Safari). Вертикальная вёрстка: `static/mobile-portrait.css`. Иконки PNG: `python scripts/generate_pwa_icons.py`.

## Запуск в Docker (на любом сервере)

В образ попадает весь проект. Поднимаются контейнер **app** (сайт) и **db** (PostgreSQL):

```bash
docker compose up -d --build
docker compose exec app python database/init_db.py
docker compose exec app python parsers/vyatsu_campus.py
```

Сайт: http://localhost:5000 (логин админа — `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `docker-compose.yml`).

### Обновление на сервере (после git push)

База **не слетает**, если не использовать `docker compose down -v`.

```bash
cd student_cabinet
git pull
docker compose exec app python database/migrate_app_settings.py
docker compose exec app python database/migrate_guard_qr.py
docker compose up -d --build
```

Первый охранник: админка → вкладка «Справка VK» → блок «Охранник». VK-токен можно ввести там же (без правки `.env`).

## Роли

- **student** — кабинет, QR-пропуск, запись к преподавателю
- **teacher** — слоты, расписание, QR-пропуск (№ удостоверения, должность, подразделение в админке)
- **guard** — страница `/guard`, сканирование QR **камерой телефона** (кнопка «Включить камеру», нужен HTTPS)
- **admin** — студенты, преподаватели, расписание, VK-токен

## Требования

- Python 3.11+
- PostgreSQL 14+ (БД `StudentCabinet`)

## Установка

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Скопируйте `.env.example` в `.env` и укажите `DATABASE_URL` и ключи.

### Яндекс.Карты (страница «Карта»)

1. [Кабинет разработчика Яндекс](https://developer.tech.yandex.ru/) — ключ с **JavaScript API**, **HTTP Геокодер**, **Маршрутизация**.
2. В `.env`: `YANDEX_MAPS_API_KEY=...`
3. Маршрут на карте: режим **auto** (по дорогам, с учётом пробок при успешном ответе API).

Координаты корпусов: `data/campus_coords.json`, синхронизация — `python parsers/vyatsu_campus.py` или кнопка в админке.

Миграция личных файлов к заметкам: `python database/migrate_note_files.py`

## Инициализация БД (отдельно от приложения)

```bash
python database/init_db.py
python database/migrate_sqlite.py   # если есть старые .db файлы
python parsers/vyatsu_campus.py     # корпуса и общежития
```

Приложение **не создаёт** таблицы при старте — только подключается к готовой БД.

## Запуск

```bash
python app.py
```

Откройте `http://127.0.0.1:5000`.

## Вход администратора

После `init_db.py`: email из `ADMIN_EMAIL` (по умолчанию `admin@vyatsu.ru`), пароль из `ADMIN_PASSWORD` (`admin123` в примере).

## VK-токен

1. Сообщество VK → Работа с API → Создать ключ (стена, документы).
2. В `.env`: `VK_ACCESS_TOKEN=...`
3. Расписание из постов: `python parsers/vk_schedule_sync.py`

Файл `vk_token.txt` не используется.

## Расписание Excel

Админ → вкладка «Расписание» или:

```bash
python schedule_parser/parse_schedule.py path/to/file.xlsx --effective-from 01.06.2026
```

## Тесты

```bash
python -m unittest tests.py
```
