r"""Clear this project's ingestion data while preserving its MySQL tables.

Run from backend/: .\.venv\Scripts\python.exe reset_data.py
Add --include-verification to also reset the optional integration-test database.
"""
import argparse
from sqlalchemy import create_engine, text
from app.db import engine


def reset(database_engine, allow_idle_worker=False):
    name = database_engine.url.database
    with database_engine.connect() as connection:
        owns_lock = connection.execute(text("SELECT GET_LOCK('threat_feed_worker', 0)")).scalar() == 1
        if not owns_lock and not allow_idle_worker:
            raise RuntimeError(f'{name}: an ingestion worker is active; stop it before resetting data')
        connection.commit()
        try:
            with connection.begin():
                active = connection.execute(text("SELECT COUNT(*) FROM ingestion_jobs WHERE state IN ('queued', 'running')")).scalar()
                if active:
                    raise RuntimeError(f'{name}: {active} job(s) are still queued or running')
                counts = {}
                for table in ('row_errors', 'ingestion_jobs', 'indicators'):
                    counts[table] = connection.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
                    connection.execute(text(f'DELETE FROM {table}'))
            print(f'{name}: cleared {counts["indicators"]} indicators, '
                  f'{counts["ingestion_jobs"]} jobs and {counts["row_errors"]} row errors')
        finally:
            if owns_lock:
                connection.execute(text("SELECT RELEASE_LOCK('threat_feed_worker')"))
                connection.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-verification', action='store_true',
                        help='also clear the separate threat_feed_verification database')
    parser.add_argument('--allow-idle-worker', action='store_true',
                        help='allow reset while a worker owns the lock, only if no jobs are queued or running')
    args = parser.parse_args()
    reset(engine, args.allow_idle_worker)
    if args.include_verification:
        verification = create_engine(engine.url.set(database='threat_feed_verification'), pool_pre_ping=True)
        reset(verification, args.allow_idle_worker)
