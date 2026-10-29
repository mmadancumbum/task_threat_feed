import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from .db import Base, engine, Session, DATA_DIR, Job, RowError

@asynccontextmanager
async def lifespan(app):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title='Threat Feed Ingestion', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['GET', 'POST'], allow_headers=['*'])

@app.get('/api/health')
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status': 'ok'}

@app.post('/api/jobs', status_code=202)
def upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(400, 'Please upload a CSV file.')
    job_id = str(uuid.uuid4())
    path = DATA_DIR / f'{job_id}.csv'
    size = 0
    try:
        with path.open('wb') as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > int(os.getenv('MAX_UPLOAD_MB', '1024')) * 1024 * 1024:
                    raise HTTPException(413, 'File exceeds the configured upload limit.')
                target.write(chunk)
        if not size:
            raise HTTPException(400, 'The file is empty.')
        with Session.begin() as session:
            session.add(Job(id=job_id, filename=file.filename.replace('\\', '/').split('/')[-1][:255], size=size))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()
    return {'id': job_id, 'state': 'queued'}

def job_dict(job):
    return {c.name: getattr(job, c.name) for c in Job.__table__.columns}

@app.get('/api/jobs')
def jobs():
    with Session() as session:
        return [job_dict(j) for j in session.scalars(select(Job).order_by(Job.created_at.desc()).limit(30))]

@app.get('/api/jobs/{job_id}')
def status(job_id: str):
    with Session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        return job_dict(job)

@app.get('/api/jobs/{job_id}/errors')
def errors(job_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    with Session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, 'Job not found')
        rows = session.scalars(select(RowError).where(RowError.job_id == job_id).order_by(RowError.id).offset(offset).limit(limit))
        return {'total': job.invalid, 'items': [{'row_number': r.row_number, 'reason': r.reason} for r in rows]}
