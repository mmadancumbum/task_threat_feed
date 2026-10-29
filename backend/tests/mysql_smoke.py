"""Explicit integration check against a separate MySQL database; retains results."""
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise SystemExit('Set DATABASE_URL in backend/.env before running this test.')
os.environ['DATABASE_URL'] = make_url(database_url).set(database='threat_feed_verification').render_as_string(hide_password=False)
os.environ['DATA_DIR'] = str(Path(__file__).resolve().parents[2] / 'data' / 'verification')

if __name__ == '__main__':
    from sqlalchemy import create_engine, text, select, func
    from fastapi.testclient import TestClient
    from app.db import engine, Base, Session, Job, Indicator
    from app.main import app
    server = create_engine(engine.url._replace(database=None), isolation_level='AUTOCOMMIT')
    with server.connect() as conn:
        conn.execute(text('CREATE DATABASE IF NOT EXISTS threat_feed_verification CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'))
    Base.metadata.create_all(engine)
    feed = Path(__file__).resolve().parents[2] / 'data' / 'generated.csv'
    subprocess.run([sys.executable, 'generate_feed.py', '--rows', '100000', '--output', str(feed)], check=True)
    worker = subprocess.Popen([sys.executable, '-m', 'app.worker'], env=os.environ.copy())
    started = time.monotonic()
    try:
        with TestClient(app) as client:
            for iteration in range(2):
                with feed.open('rb') as upload:
                    response = client.post('/api/jobs', files={'file': ('generated.csv', upload, 'text/csv')})
                assert response.status_code == 202, response.text
                job_id = response.json()['id']
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    result = client.get(f'/api/jobs/{job_id}').json()
                    if result['state'] in ('completed', 'failed'):
                        break
                    time.sleep(.2)
                assert result['state'] == 'completed', result
                assert result['processed'] == 100000 and result['invalid'] == 0, result
                assert result['new'] + result['merged'] == 100000
                if iteration == 1:
                    assert result['new'] == 0 and result['merged'] == 100000, result
                print({k: result[k] for k in ('state', 'processed', 'new', 'merged', 'invalid')})
            with Session() as session:
                assert session.scalar(select(func.count()).select_from(Indicator)) == 80000
                # Overlapping generated rows must preserve maximum confidence.
                indicator = session.scalar(select(Indicator).where(Indicator.value == 'host-0.example'))
                assert indicator.confidence == 80000 % 101
            print(f'MySQL integration and idempotency passed in {time.monotonic() - started:.1f}s')
    finally:
        worker.terminate()
        worker.wait(timeout=15)
