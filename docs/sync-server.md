# Сервер синхронизации LanDesigner

LanDesigner хранит рабочий проект локально в `.lanproj`. Сервер синхронизации — общий каталог проектов для команды: те же UUID и `revision`, обмен целым файлом проекта (blob).

Клиент в GUI: меню **Синхронизация**.

## Установка зависимостей

```bash
pip install -e ".[remote]"
```

В состав входят FastAPI, Uvicorn, HTTP-клиент и драйвер PostgreSQL (`psycopg`).

## Запуск (SQLite, локально)

По умолчанию данные сервера — файл SQLite:

```bash
python -m server --host 127.0.0.1 --port 8765
```

Файл БД: `data/landesigner_server.db` (или `--db путь/к/файлу.db`).

Проверка: `GET http://127.0.0.1:8765/health` → `{"status":"ok"}`.

## PostgreSQL

```bash
export LANDESIGNER_DATABASE_URL="postgresql://user:pass@localhost:5432/landesigner"
python -m server --database-url "$LANDESIGNER_DATABASE_URL"
```

Таблица `projects` создаётся при старте:

| Поле | Тип |
|------|-----|
| `id` | UUID |
| `name` | текст |
| `revision` | integer |
| `updated_at` | timestamptz |
| `data` | bytea (содержимое `.lanproj`) |

Приоритет бэкенда: `LANDESIGNER_DATABASE_URL` → SQLite.

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

| Параметр | Значение по умолчанию |
|----------|------------------------|
| API | `http://127.0.0.1:8765` |
| API-ключ | `dev-secret` (`LANDESIGNER_API_KEY` в `.env`) |
| PostgreSQL | пользователь/БД `landesigner`, volume `pgdata` |

Остановка: `docker compose down` (данные PostgreSQL сохраняются в volume).

## Авторизация

Опционально на сервере:

```bash
export LANDESIGNER_API_KEY=ваш-секрет
python -m server
```

Тот же ключ укажите в GUI: **Синхронизация → Настройки сервера**.

Без ключа сервер принимает запросы без проверки (удобно для локальной отладки).

Заголовки клиента: `X-API-Key: …` или `Authorization: Bearer …`.

## Сценарии в GUI

| Действие | Когда использовать |
|----------|-------------------|
| **Настройки сервера** | URL и API-ключ; кнопка «Проверить соединение» |
| **Клонировать с сервера** | Скачать чужой проект как новый `.lanproj` |
| **Опубликовать** | Первый upload локального проекта на сервер |
| **Push** | Отправить локальные изменения (optimistic lock по `revision`) |
| **Pull** | Забрать серверную версию (перезаписать локальный snapshot) |

После публикации рядом с `.lanproj` появляется `.lanproj.sync.json` (remote id, URL, revision).

## Конфликты revision

При Push, если на сервере другая `revision`, показывается диалог:

- **Оставить локальное** — отмена push
- **Принять серверное** — pull и замена локальных данных
- **Diff** — сравнение метаданных локальной и серверной копии
- **Принудительный push** — перезаписать сервер (осторожно)

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `LANDESIGNER_HOST` | Хост bind (по умолчанию `127.0.0.1`) |
| `LANDESIGNER_PORT` | Порт (по умолчанию `8765`) |
| `LANDESIGNER_SERVER_DB` | Путь SQLite-файла |
| `LANDESIGNER_DATABASE_URL` | DSN PostgreSQL |
| `LANDESIGNER_API_KEY` | Ожидаемый API-ключ |

## API (кратко)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка живости |
| GET | `/projects` | Список проектов |
| GET | `/projects/{id}` | Тело `.lanproj` + заголовки revision |
| POST | `/projects` | Создание (заголовки `X-Project-Id`, `X-Project-Name`, `X-Revision`) |
| PUT | `/projects/{id}` | Push (`If-Match: revision`, тело — blob) |

Подробная реализация: `server/app.py`, `server/store.py`.
