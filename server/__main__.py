from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="LanDesigner Sync Server")
    parser.add_argument("--host", default=os.environ.get("LANDESIGNER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LANDESIGNER_PORT", "8765")))
    parser.add_argument(
        "--db",
        default=os.environ.get("LANDESIGNER_SERVER_DB", "data/landesigner_server.db"),
        help="SQLite-файл (если не задан --database-url / LANDESIGNER_DATABASE_URL)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LANDESIGNER_DATABASE_URL", ""),
        help="PostgreSQL DSN, напр. postgresql://user:pass@localhost/landesigner",
    )
    args = parser.parse_args()
    if args.database_url:
        os.environ["LANDESIGNER_DATABASE_URL"] = args.database_url
    else:
        os.environ["LANDESIGNER_SERVER_DB"] = args.db

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Нужны зависимости сервера: pip install 'lan-designer[remote]' "
            "или pip install fastapi uvicorn"
        ) from exc

    from server.app import create_app
    from server.store import create_project_store

    app = create_app(create_project_store(db_path=args.db, database_url=args.database_url or None))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
