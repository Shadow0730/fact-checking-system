"""Apply db/init.sql to DATABASE_URL. Only needed if you run Postgres (with pgvector) without
Docker; the Docker image applies init.sql automatically on first start.

    uv run python scripts/init_db.py
"""
import _bootstrap  # noqa: F401

from app.config import REPO_DIR
from app.db import engine


def main() -> None:
    sql = (REPO_DIR / "db" / "init.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)
    print("Schema applied.")


if __name__ == "__main__":
    main()
