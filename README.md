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

Опционально: `LANDESIGNER_API_KEY=секрет` на сервере; тот же ключ в **Синхронизация → Настройки сервера**.

В GUI: клонировать / опубликовать / Push / Pull. Конфликты по `revision`: оставить локальное, принять серверное или принудительный push.

Хранилище сервера по умолчанию — SQLite (`data/landesigner_server.db`); контракт готов к замене на PostgreSQL.
