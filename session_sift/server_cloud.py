from __future__ import annotations

from session_sift.cloud.api import create_cloud_app


def main(host: str = "127.0.0.1", port: int = 9980, db_path: str = ".session-sift/team-cloud.db") -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("FastAPI cloud dependencies are missing. Install with: pip install -e .[cloud]") from exc

    app = create_cloud_app(db_path=db_path)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()