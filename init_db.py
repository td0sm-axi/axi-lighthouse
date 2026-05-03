"""
Creates all database tables. Safe to run multiple times (create_all is idempotent).

Usage:
    python init_db.py
"""
from db.session import engine, DATABASE_URL
from db.models import Base


def init():
    Base.metadata.create_all(engine)
    print(f"Database initialised: {DATABASE_URL}")
    print("Tables: mentions, crawler_runs")


if __name__ == "__main__":
    init()
