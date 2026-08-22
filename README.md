# LanDesigner

Десктоп-приложение для проектирования и инвентаризации ЛВС: **LAN CAD + CMDB lite**.

## Запуск

```bash
python main.py
```

## Синхронизация (этап 6)

Локальный `.lanproj` — рабочий offline-кэш. Общий репозиторий — HTTP API.

```bash
pip install -e ".[remote]"
python -m server --host 127.0.0.1 --port 8765
```

**SQLite (по умолчанию):** файл `data/landesigner_server.db` или `--db путь/к/файлу.db`.

**PostgreSQL:**

```bash
export LANDESIGNER_DATABASE_URL="postgresql://user:pass@localhost:5432/landesigner"
python -m server --database-url "$LANDESIGNER_DATABASE_URL"
```

**Docker Compose (PostgreSQL + сервер):**

```bash
cp .env.example .env
docker compose up -d --build
```

- API: `http://127.0.0.1:8765`
- Ключ по умолчанию: `dev-secret` (переменная `LANDESIGNER_API_KEY` в `.env`)
- В GUI (**Синхронизация → Настройки сервера**): URL `http://127.0.0.1:8765`, тот же API-ключ

Остановка: `docker compose down`. Данные PostgreSQL сохраняются в volume `pgdata`.

Таблица `projects` создаётся автоматически при старте (UUID, revision, blob `.lanproj`).

Опционально: `LANDESIGNER_API_KEY=секрет` на сервере; тот же ключ в **Синхронизация → Настройки сервера**.

В GUI: клонировать / опубликовать / Push / Pull. Конфликты по `revision`: оставить локальное, принять серверное или принудительный push.
