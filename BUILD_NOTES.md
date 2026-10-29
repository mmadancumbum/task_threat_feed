# Build and AI assistance notes

- Date: 29 October 2026, Asia/Kolkata (UTC+05:30).
- First task prompt: 17:28:29 IST, from the local Codex session record.
- At 17:39:19 IST, the core implementation, 16 automated tests, frontend production build and real MySQL 100k-row repeat-ingestion test were complete. Documentation and local HTTP readiness checks followed.
- Local frontend and API proxy checks passed at 17:42:33 IST. Elapsed from first task prompt to this working-app checkpoint: 14 minutes 4 seconds.
- Primary Codex session usage for that build window, measured from the token count before the first task prompt through the working-app checkpoint: **1,105,646 input tokens** (including **1,070,336 cached input tokens**), **23,692 output tokens** (including **1,615 reasoning tokens**), **1,129,338 total tokens**. These are from the local primary session log; they exclude subsequent support turns and any auxiliary review processes.
- The assessment's large CSV was not attached. A deterministic local generator supplies a separate 100,000-row test file with known merge counts.
- Both project databases were subsequently reset at the user's request. The verification results above refer to the completed integration run, not the current database contents.
- The local database password was moved to ignored `.env` files and redacted from the public prompt log before publishing the repository.

## Where AI needed correction

1. The initial database bootstrap used SQLAlchemy `URL.set(database=None)`, which retains the previous database. This caused an unknown-database error before creation. It was corrected to clear the database explicitly using `_replace(database=None)`; creation and the subsequent MySQL integration test passed.
2. PowerShell blocks the `npm.ps1` wrapper on this machine. Commands use `npm.cmd` and the virtual environment's Python directly, avoiding execution-policy changes.
3. Progress was implemented as processed-record counts instead of a fabricated percentage. A total requires an additional full scan; the chosen implementation streams once and records the total at EOF.

## Submission preparation

Review and understand normalization, batch atomicity, worker locking and recovery before the interview. Repository: [mmadancumbum/task_threat_feed](https://github.com/mmadancumbum/task_threat_feed). Application deployment was not performed by this session.
