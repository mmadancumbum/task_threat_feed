import csv
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app import db, worker, main
from app.validation import normalize

@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'test.db'), connect_args={'check_same_thread': False})
    db.Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    for module in (worker, main):
        monkeypatch.setattr(module, 'Session', factory)
        monkeypatch.setattr(module, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(main, 'engine', engine)
    yield factory, tmp_path
    engine.dispose()

def row(**changes):
    return dict(indicator='EXAMPLE.COM', type='domain', confidence='50', source='test', first_seen='2026-01-01', **{}) | changes

@pytest.mark.parametrize('changes', [dict(type='unknown'), dict(indicator='999.1.1.1', type='ipv4'), dict(type='md5', indicator='abcd'), dict(type='sha256', indicator='f'*63), dict(confidence='1.1'), dict(confidence='101'), dict(confidence='-1'), dict(first_seen='yesterday'), dict(source=''), dict(indicator='https://bad host/', type='url'), dict(indicator='https://example.com:99999', type='url')])
def test_invalid_rows(changes):
    with pytest.raises(ValueError):
        normalize(row(**changes))

def test_normalization():
    assert normalize(row())['value'] == 'example.com'
    assert normalize(row(indicator='example.com.'))['key'] == normalize(row())['key']
    assert normalize(row(type='md5', indicator='A'*32))['value'] == 'a'*32
    assert normalize(row(type='url', indicator='HTTPS://EXAMPLE.COM:443/Path?q=A#fragment'))['value'] == 'https://example.com/Path?q=A'
    assert normalize(row(first_seen='2026-01-01T02:00:00+02:00'))['first_seen'].hour == 0

def add_job(store, rows):
    factory, directory = store
    job_id = str(uuid4())
    path = directory / f'{job_id}.csv'
    with path.open('w', newline='') as feed:
        writer = csv.DictWriter(feed, fieldnames=['indicator', 'type', 'confidence', 'source', 'first_seen'])
        writer.writeheader()
        writer.writerows(rows)
    with factory.begin() as session:
        session.add(db.Job(id=job_id, filename='test.csv', size=path.stat().st_size))
    return job_id

def test_merge_reupload_and_error_reporting(store):
    factory, _ = store
    values = [row(), row(indicator='example.com.', confidence='90', first_seen='2025-01-01'), row(type='ipv4', indicator='999.1.1.1')]
    first = add_job(store, values)
    worker.process(first)
    second = add_job(store, values)
    worker.process(second)
    with factory() as session:
        a, b = session.get(db.Job, first), session.get(db.Job, second)
        assert (a.state, a.new, a.merged, a.invalid, a.processed) == ('completed', 1, 1, 1, 3)
        assert (b.new, b.merged, b.invalid) == (0, 2, 1)
        indicators = session.scalars(select(db.Indicator)).all()
        assert len(indicators) == 1
        assert indicators[0].confidence == 90
        assert indicators[0].first_seen.year == 2025
        assert a.breakdown == {'domain': 2}
        assert session.scalar(select(db.RowError).where(db.RowError.job_id == first)).row_number == 4

def test_resume_after_committed_batch(store, monkeypatch):
    factory, _ = store
    job_id = add_job(store, [row(indicator=f'host-{i}.example') for i in range(7)])
    monkeypatch.setattr(worker, 'BATCH_SIZE', 3)
    real_session = worker.Session
    calls = 0
    class InterruptedSession:
        def begin(self):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise KeyboardInterrupt()
            return real_session.begin()
    monkeypatch.setattr(worker, 'Session', InterruptedSession())
    with pytest.raises(KeyboardInterrupt):
        worker.process(job_id)
    with factory() as session:
        assert session.get(db.Job, job_id).processed == 3
    monkeypatch.setattr(worker, 'Session', real_session)
    worker.process(job_id)
    with factory() as session:
        job = session.get(db.Job, job_id)
        assert (job.state, job.processed, job.new, job.merged) == ('completed', 7, 7, 0)
        assert session.scalar(select(func.count()).select_from(db.Indicator)) == 7

def test_bad_headers_fail_job(store):
    factory, directory = store
    job_id = add_job(store, [])
    (directory / f'{job_id}.csv').write_text('wrong,headers\n1,2\n')
    worker.process(job_id)
    with factory() as session:
        assert session.get(db.Job, job_id).state == 'failed'

def test_upload_api_returns_before_processing(store):
    with TestClient(main.app) as client:
        result = client.post('/api/jobs', files={'file': ('sample.csv', Path(__file__).parents[2].joinpath('data/sample.csv').read_bytes(), 'text/csv')})
        assert result.status_code == 202
        job_id = result.json()['id']
        assert client.get(f'/api/jobs/{job_id}').json()['state'] == 'queued'
        worker.process(job_id)
        result = client.get(f'/api/jobs/{job_id}').json()
        assert (result['new'], result['merged'], result['invalid']) == (5, 1, 3)
        assert len(client.get(f'/api/jobs/{job_id}/errors?limit=2').json()['items']) == 2
        assert client.get('/api/jobs/not-found').status_code == 404
        assert client.post('/api/jobs', files={'file': ('empty.csv', b'')}).status_code == 400
        assert client.post('/api/jobs', files={'file': ('bad.txt', b'hello')}).status_code == 400
