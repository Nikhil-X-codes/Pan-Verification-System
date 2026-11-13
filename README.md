# PAN Verification System

Delivery milestone 1 of 3: a FastAPI backend with persistent SQLite storage. The implementation is complete locally; remaining source is being published in separate feature batches at least four hours apart. See [PUBLISHING.md](PUBLISHING.md) for delivery and commit guidelines.

## Run the backend

1. Install Python 3.11 or newer.
2. Run `python -m pip install -r backend/requirements-dev.txt`.
3. Run `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log`.
4. Check `http://localhost:8000/health`.
5. Run `python -m pytest backend/tests -q` for backend tests over real HTTP.

## Included features

- PAN normalization and validation before database lookup.
- Vendor A and Vendor B with configurable faults and failover.
- Persistent idempotency keys and PAN fingerprints, with byte-identical replay.
- Atomic response and ledger commits, stale-owner fencing and crash recovery.
- `/verify/pan`, `/charges`, `/reconcile` and `/health` endpoints.
- 34 locally passing backend cases covering both primaries, failure, concurrency, crash and privacy behavior.

`PRIMARY` defaults to `a`. `FAULT_VENDORS` defaults to `a`; an empty value disables faults. `DATABASE_PATH` defaults to `data/pan.sqlite3`. `CRASH_POINT` is off unless set to `after_vendor_call` or `after_vendor_persist`.

React is the next publishing batch. Docker, gateway, CI and the full README and runbook follow in the final batch. Their absence here is intentional.
