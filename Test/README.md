# Test — локальный сайт по HTTPS

Отдельная копия проекта для проверки с телефона (камера охранника на iPhone нужен HTTPS).

## Быстрый старт

```powershell
cd Test
.\start.ps1
```

При первом запуске скрипт скопирует проект в `Test\run\` и поднимет Docker.

- **ПК и телефон (HTTPS):** https://127.0.0.1:5443 или https://\<IP_из_ipconfig\>:5443  

Порт **5000** не используется — чтобы не мешать основному `docker compose` в корне проекта.

На iPhone при предупреждении о сертификате: **Подробнее → перейти** (это dev-сертификат).

## Вручную

```powershell
.\setup.ps1
python generate_dev_https.py 192.168.137.1
docker compose up -d --build
```

IP укажите из `ipconfig` (адаптер мобильного хот-спота, часто `192.168.137.1`).

## База

Отдельный том `test_pgdata` — не трогает основную БД в корне проекта.

Инициализация (один раз):

```powershell
docker compose exec app python database/init_db.py
docker compose exec app python database/migrate_guard_qr.py
```

## Остановка

```powershell
docker compose down
```

Полное удаление копии и БД теста: удалите папки `run\` и том Docker `test_pgdata`.
