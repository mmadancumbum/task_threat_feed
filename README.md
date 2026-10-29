# Signal — Threat feed ingestion

FastAPI + React + MySQL implementation of the engineering assessment. Upload a CSV, receive a job ID, follow background processing, and inspect new/merged/invalid counts, type totals, and paginated validation errors. No authentication is required for this local assessment.

## Run locally on Windows (PowerShell)

Prerequisites: Python 3.13, Node.js 22.12+ (tested with 24.21), and a running MySQL 8 server at `127.0.0.1:3306`. An existing Python virtual environment and installed frontend dependencies are provided in this workspace; the setup commands below also work from a fresh checkout. Store the database password only in ignored local `.env` files or process environment variables.

### 1. One-time setup

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
python -m venv .venv
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and replace YOUR_MYSQL_PASSWORD with your local MySQL password.
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe init_db.py

Set-Location '..\frontend'
npm.cmd ci
```

`init_db.py` creates the `threat_feed` database if needed, then creates tables without deleting existing data. It has already run successfully on this machine. Set `DATABASE_URL` in the ignored `backend/.env` file before running it. `DATA_DIR` paths are relative to the backend process working directory; both backend processes must use the same directory.

To clear the app's indicators and job history before another test, stop the worker and run:

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
.\.venv\Scripts\python.exe reset_data.py
```

Add `--include-verification` to clear the separate `threat_feed_verification` database too. The command preserves tables and CSV files, and refuses to run while jobs are queued/running or a worker holds the database lock.
If a worker is still running but idle, add `--allow-idle-worker`; this checks that no jobs are queued or running before clearing. Do not upload a file during the reset.

### 2. Terminal 1 — API

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API documentation: <http://127.0.0.1:8000/docs>

### 3. Terminal 2 — background worker

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
.\.venv\Scripts\python.exe -m app.worker
```

Keep the worker running: uploads stay `queued` until it starts.

### 4. Terminal 3 — React frontend

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\frontend'
npm.cmd run dev
```

Open <http://127.0.0.1:5173>. Select a CSV, click **Start ingestion**, and watch the activity and summary. Use Ctrl+C in each terminal to stop. These commands do not activate the virtual environment or require changing PowerShell's execution policy; `npm.cmd` also avoids the blocked `npm.ps1` wrapper.

## Test files

- `data/sample.csv`: 9 rows covering all five types. A fresh database should report **5 new, 1 merged, 3 invalid**. Repeat upload: **0 new, 6 merged, 3 invalid**.
- `data/generated.csv`: the supplied local **100,000-row file**, about 5 MB. It contains **80,000 unique domains**, 20,000 duplicate rows, and no invalid rows. First upload to a fresh application database: **80,000 new, 20,000 merged, 0 invalid**. Second upload: **0 new, 100,000 merged, 0 invalid**.

The generated file and uploaded data are ignored by Git. The original assessment's feed was not supplied; place it in `data/` or upload it from its existing location. To regenerate the large test file:

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
.\.venv\Scripts\python.exe generate_feed.py --rows 100000 --output ../data/generated.csv
```

CSV header (exact, unique column names; order can vary):

```csv
indicator,type,confidence,source,first_seen
Example.COM,domain,80,partner,2026-01-01
```

## Architecture and decisions

```text
React -- multipart upload --> FastAPI -- stream to disk --> shared uploads
                              |                                |
                              +--> MySQL job (queued)          |
                                      |                        |
Separate Python worker <--- DB poll ---+------ CSV streaming <--+
       |                                      |
       +---- 500-row transaction batches ------+
       |         indicators + errors + checkpoint
       v
MySQL status <-- FastAPI status polling <-- React (1.5 seconds)
```

- Upload handling copies chunks to a server-generated filename and queues a durable MySQL job. HTTP 202 is returned after receiving/saving the upload, before parsing or ingestion. Client filenames never determine filesystem paths.
- A separate worker polls MySQL, so ingestion survives API restarts. This deliberately avoids Redis/Celery for a small assessment.
- A MySQL named lock permits one ingestion worker across processes. It serializes merge decisions and prevents concurrent jobs from counting the same indicator as new. A second worker exits without processing. This is a throughput tradeoff, not a horizontally scaled queue.
- Files stream through Python's CSV reader; only 500 rows and matching existing indicators are kept in memory per batch. Validation errors are stored separately and paginated rather than kept in RAM or returned in a giant response.
- Each batch transaction commits indicators, validation errors, summary counters, and the processed-record checkpoint together. A worker killed between batches can resume the `running` job by skipping already committed records. Recovery re-reads the file from the beginning with bounded memory. Fatal job errors produce `failed`; committed earlier batches remain stored.
- Progress is a live processed-row count with an indeterminate bar until completion. The total is recorded at EOF, avoiding an extra whole-file scan just to calculate a percentage.
- Keys are SHA-256 of type, a null separator, and normalized value, enforced by the indicator primary key. This accommodates long URLs without MySQL index-size problems. Exact type/value matches are checked when merging; a hypothetical hash collision fails the job.
- Within a batch, duplicates are merged in memory; existing keys are fetched in one query. Confidence is the maximum and `first_seen` the minimum. Repeated uploads leave indicator data unchanged.
- The type breakdown counts **valid input rows**, including merges. Therefore the type totals sum to `new + merged`, and `processed = new + merged + invalid` for completed jobs.

## Domain and security assumptions

- Supported types are `ipv4`, `domain`, `url`, `md5`, `sha256`; surrounding whitespace and type letter casing are normalized.
- IPv4 uses Python's strict address parser. Domains use lowercase IDNA, remove a terminal dot, require at least two valid labels, and reject empty/invalid labels. Single-label internal hostnames and wildcards are not supported.
- URLs must be HTTP(S), have a valid host and port, and contain no credentials or whitespace. Scheme and host casing are normalized, default ports and fragments removed, and empty paths become `/`. Path/query case and query parameter order are preserved because they can change resource identity. IPv6 is allowed inside URLs, but there is no standalone `ipv6` IOC type. Feeds are never fetched or visited.
- Hashes must have exactly 32/64 hexadecimal characters; stored lowercase.
- Confidence must be an integer from 0 to 100. Dates/datetimes must parse as ISO-8601; offsets become naive UTC for MySQL. Date-only and timezone-free values are assumed UTC. No business rule rejects future dates.
- Every required field must be present and nonempty. Source length is capped at 255 characters; the first stored source is retained when merging. Full source provenance is a future improvement.
- Row error numbers refer to the CSV's physical ending line, including the header; a quoted multiline record can span several lines. Bad row values are counted and skipped. Invalid encoding, broken CSV quoting, or missing/duplicate headers fail the job because record boundaries/schema are unreliable.
- Indicator length is capped at 8,192 characters. Maximum application upload size defaults to 1,024 MB; exceeding it returns HTTP 413. The multipart parser may spool data before this handler, so use a reverse-proxy request limit for externally exposed deployment.
- No authentication, tenant separation, or rate limit is included per the assessment. The local database account is configured in ignored `.env` files. Before external deployment, configure a dedicated DB account, secret management, HTTPS, authentication/access restrictions, upload limits and retention. Uploaded files and errors are retained; no cleanup task runs automatically.

## API

| Method | Endpoint | Result |
|---|---|---|
| GET | `/api/health` | Database connectivity check |
| POST | `/api/jobs` | Multipart `file`; HTTP 202 `{id, state}` |
| GET | `/api/jobs` | Latest 30 jobs |
| GET | `/api/jobs/{id}` | State, counters, progress, type breakdown and failure reason |
| GET | `/api/jobs/{id}/errors?offset=0&limit=50` | Paginated `{total, items: [{row_number, reason}]}`; max page size 200 |

States: `queued → running → completed`, or `failed`. The initial total is `null` until processing completes. Missing jobs return 404; invalid file extension/empty uploads return 400.

Example upload from another PowerShell terminal:

```powershell
curl.exe -F "file=@D:\Drive 1\Interview task\threat-feed\data\generated.csv" http://127.0.0.1:8000/api/jobs
```

## Verification

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed\backend'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# Optional: real 100k-row integration test in a SEPARATE database.
# Uses credentials from the ignored backend/.env file and creates
# threat_feed_verification. It retains test data and regenerates generated.csv.
.\.venv\Scripts\python.exe tests/mysql_smoke.py

Set-Location '..\frontend'
npm.cmd run build
```

Verified during this build: 16 automated tests passed; React production build passed; a separate MySQL worker processed 100,000 rows twice in 39 seconds total, producing 80,000 unique indicators, then zero new indicators on repeat. Local frontend and API proxy HTTP checks passed. Both MySQL databases were subsequently reset at the user's request; the generated CSV and ignored uploaded files remain on disk. Browser visual testing and Docker deployment were not performed. The installed Starlette version emits a deprecation warning for its HTTPX test adapter; the tests pass.

## Docker deployment

From the project root:

```powershell
Set-Location 'D:\Drive 1\Interview task\threat-feed'
# Create an ignored .env file containing MYSQL_ROOT_PASSWORD=<your chosen password>.
docker compose up --build -d
docker compose logs -f api worker
```

Open <http://localhost:8080>. Compose starts isolated MySQL, API, worker, and Nginx serving the React build. MySQL is not published on the host, so it can coexist with your local MySQL service. Persistent volumes store the DB and shared uploads. MySQL's `MYSQL_DATABASE` initializes the database on first startup; API/worker create tables with `create_all`. No seed is required. Nginx forwards `/api` to FastAPI and limits uploads to 1 GB.

Environment: `DATABASE_URL` (SQLAlchemy MySQL URL), `DATA_DIR` (shared absolute upload directory), `MAX_UPLOAD_MB` (optional, default 1024). Compose supplies the first two from its configuration and requires `MYSQL_ROOT_PASSWORD` in the ignored project root `.env` or the process environment. If the password contains URL-reserved characters, encode it in `DATABASE_URL` before using Compose. MySQL initialization variables affect fresh volumes only. Deploy on a Docker host, configure secrets and HTTPS/access restrictions, then use the same commands. For future schema changes, add a versioned migration tool such as Alembic; `create_all` does not alter existing tables.

```powershell
docker compose down
```

This stops containers while preserving their data volumes.

## Submission notes and limitations

See `PROMPTS.md` and `BUILD_NOTES.md` for the actual user prompts, observed timing, AI correction notes and usage-reporting limits. The source repository is [mmadancumbum/task_threat_feed](https://github.com/mmadancumbum/task_threat_feed). Do not add `.env`, the generated 100k CSV, or runtime data. The original assessment CSV, exact token usage, and exact first-prompt timestamp still need to be supplied by the applicant before final submission.

Next improvements: parallel job leasing with atomic MySQL upserts and reliable new/merged accounting, bounded request streaming before multipart spooling, file retention/cleanup, source provenance, database migrations, indexes for high-volume error pagination, frontend browser tests, and cancellation/retry controls. The UI shows only the latest 30 jobs. One worker handles all ingestion sequentially. This is intended as a readable assessment core that can be explained in an interview.

Implementation references: [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/) and [SQLAlchemy ORM data operations](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html).
