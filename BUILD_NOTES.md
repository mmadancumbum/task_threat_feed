# Build and AI assistance notes

- Date: 29 October 2026, Asia/Kolkata (UTC+05:30).
- First recorded build timestamp: 17:29:53 IST. PDF/workspace review began earlier; the exact first task-prompt timestamp is not available in this session, so this is not claimed as the exact start time.
- At 17:39:19 IST, the core implementation, 16 automated tests, frontend production build and real MySQL 100k-row repeat-ingestion test were complete. Documentation and local HTTP readiness checks followed.
- Local frontend and API proxy checks passed at 17:42:33 IST. Elapsed from first recorded build timestamp: approximately 12 minutes 40 seconds. The full first-prompt-to-finish duration is unavailable because the first-prompt timestamp was not exposed.
- Exact input/output token totals are not exposed to this coding session. Obtain actual usage from the product/account usage export before submitting; no token count is invented here.
- The assessment's large CSV was not attached. A deterministic local generator supplies a separate 100,000-row test file with known merge counts.
- Both project databases were subsequently reset at the user's request. The verification results above refer to the completed integration run, not the current database contents.
- The local database password was moved to ignored `.env` files and redacted from the public prompt log before publishing the repository.

## Where AI needed correction

1. The initial database bootstrap used SQLAlchemy `URL.set(database=None)`, which retains the previous database. This caused an unknown-database error before creation. It was corrected to clear the database explicitly using `_replace(database=None)`; creation and the subsequent MySQL integration test passed.
2. PowerShell blocks the `npm.ps1` wrapper on this machine. Commands use `npm.cmd` and the virtual environment's Python directly, avoiding execution-policy changes.
3. Progress was implemented as processed-record counts instead of a fabricated percentage. A total requires an additional full scan; the chosen implementation streams once and records the total at EOF.

## Submission preparation

Review and understand normalization, batch atomicity, worker locking and recovery before the interview. Supply the actual account usage/token report and accurate first-prompt/build timing if available externally. Repository: [mmadancumbum/task_threat_feed](https://github.com/mmadancumbum/task_threat_feed). Application deployment was not performed by this session.
