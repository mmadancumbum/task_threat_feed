"""One DB-locked worker; each batch commits data and its checkpoint atomically."""
import csv
import logging
import time
from itertools import islice
from sqlalchemy import select, text
from .db import Base, engine, Session, DATA_DIR, Job, Indicator, RowError
from .validation import normalize, FIELDS

log = logging.getLogger(__name__)
BATCH_SIZE = 500

def process(job_id, check_lock=lambda: None):
    try:
        with Session.begin() as session:
            job = session.get(Job, job_id)
            job.state = 'running'
            checkpoint = job.processed
        with (DATA_DIR / f'{job_id}.csv').open(encoding='utf-8-sig', newline='') as feed:
            reader = csv.DictReader(feed, strict=True)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(FIELDS):
                raise ValueError('CSV must have exactly these unique headers: ' + ', '.join(FIELDS))
            # Re-read only on recovery; memory remains bounded for arbitrarily large feeds.
            for _ in islice(reader, checkpoint):
                pass
            while True:
                batch = []
                for _ in range(BATCH_SIZE):
                    try:
                        row = next(reader)
                    except StopIteration:
                        break
                    batch.append((reader.line_num, row))
                if not batch:
                    break
                check_lock()
                with Session.begin() as session:
                    job = session.get(Job, job_id)
                    valid = []
                    for line, row in batch:
                        try:
                            valid.append(normalize(row))
                        except ValueError as exc:
                            job.invalid += 1
                            session.add(RowError(job_id=job_id, row_number=line, reason=str(exc)[:500]))
                    keys = [v['key'] for v in valid]
                    existing = {v.key: v for v in session.scalars(select(Indicator).where(Indicator.key.in_(keys)))} if keys else {}
                    counts = dict(job.breakdown)
                    for value in valid:
                        counts[value['type']] = counts.get(value['type'], 0) + 1
                        known = existing.get(value['key'])
                        if known is None:
                            known = Indicator(**value)
                            session.add(known)
                            existing[value['key']] = known
                            job.new += 1
                        else:
                            if known.type != value['type'] or known.value != value['value']:
                                raise ValueError('indicator key collision')
                            known.confidence = max(known.confidence, value['confidence'])
                            known.first_seen = min(known.first_seen, value['first_seen'])
                            job.merged += 1
                    job.breakdown = counts
                    job.processed += len(batch)
        with Session.begin() as session:
            job = session.get(Job, job_id)
            job.state, job.total = 'completed', job.processed
    except Exception as exc:
        log.exception('Job %s failed', job_id)
        with Session.begin() as session:
            job = session.get(Job, job_id)
            job.state = 'failed'
            job.error = str(exc)[:1000] if isinstance(exc, (ValueError, UnicodeError, csv.Error)) else 'Processing failed; check worker logs.'

def main():
    logging.basicConfig(level=logging.INFO)
    Base.metadata.create_all(engine)
    # Dedicated connection owns the lock throughout processing. Multiple worker
    # processes cannot race their read/merge/write or checkpoint recovery.
    with engine.connect() as lock:
        if lock.execute(text("SELECT GET_LOCK('threat_feed_worker', 0)")).scalar() != 1:
            raise SystemExit('Another worker is already active.')
        try:
            def check_lock():
                if lock.execute(text("SELECT IS_USED_LOCK('threat_feed_worker') = CONNECTION_ID()")).scalar() != 1:
                    raise RuntimeError('Worker no longer owns its database lock')
            while True:
                check_lock()
                with Session() as session:
                    job_id = session.scalar(select(Job.id).where(Job.state.in_(['queued', 'running'])).order_by(Job.created_at).limit(1))
                if job_id:
                    process(job_id, check_lock)
                else:
                    time.sleep(1)
        finally:
            lock.execute(text("SELECT RELEASE_LOCK('threat_feed_worker')"))

if __name__ == '__main__':
    main()
