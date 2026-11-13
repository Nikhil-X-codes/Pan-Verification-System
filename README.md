# PAN Verification System

Delivery milestone 2 of 5: the SQLite-backed FastAPI service and React verification page. The implementation is complete locally; source is being published in batches at least four hours apart. See [PUBLISHING.md](PUBLISHING.md) for delivery and commit guidelines.

## Run locally

1. Install Python 3.11+ and Node 22.4+.
2. Run `python -m pip install -r backend/requirements-dev.txt`.
3. Run `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log`.
4. In another terminal run `cd frontend`, `npm ci`, then `npm run dev`.
5. Open `http://localhost:5173`; Vite proxies `/api` to the backend.
6. Run `python -m pytest backend/tests -q` from the root and `npm test` inside `frontend`.

## Included features

The backend provides validation, asynchronous fake providers, persistent idempotency, atomic billing, reconciliation and crash recovery. Its 34 local tests passed over real HTTP.

React 18 uses TypeScript strict mode, live validation, UUID attempt keys, safe retries, bounded automatic retries, fast-response double-click protection and masked history. Fifteen frontend tests passed. Keyboard submission, visible focus and a 360 px mobile layout were checked in Chrome. Production JavaScript measured 48,884 bytes gzipped.

Docker, Nginx and Make targets arrive in batch 3, GitHub Actions in batch 4, and the operating guide and complete acceptance documentation in batch 5. Their absence here is intentional.
