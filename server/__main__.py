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
    )
    args = parser.parse_args()
    os.environ["LANDESIGNER_SERVER_DB"] = args.db

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Нужны зависимости сервера: pip install 'lan-designer[remote]' "
            "или pip install fastapi uvicorn"
        ) from exc

    from server.app import create_app
    from server.store import ProjectStore

    app = create_app(ProjectStore(args.db))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
