# IDTO PAN verification

FastAPI, React 18, TypeScript strict mode, persistent SQLite and an Nginx gateway serving two backend replicas. Vendor A and Vendor B are asynchronous fake providers using only the assignment's sample records.

## Setup

1. Start Docker Desktop or Docker Engine, with Compose v2, GNU Make and Bash on PATH.
2. Copy `.env.example` to `.env` if you want to change defaults.
3. Run `make up`.
4. Open <http://localhost:8080>; the API is under `/api`.
5. Direct backend health is <http://localhost:8001/health>.
6. Run `make test` for isolated backend and frontend tests, with automatic cleanup.
7. Run `FAULT_VENDORS= CRASH_POINT= make up`, then `make load`.
8. Run `make down` to stop without deleting the database volume.

## Local development

Python 3.11+ and Node 22.4+ are required for development outside Docker. Install Python dependencies with `python -m pip install -r backend/requirements-dev.txt`. Start `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log`. In another terminal run `cd frontend`, `npm ci`, then `npm run dev`. Vite serves the app at <http://localhost:5173> and proxies `/api` to the local backend. Stop each process with Ctrl+C.

On the current Windows workspace, Python was downloaded into `.tools/python`, which is ignored by Git. Substitute `.tools\python\python.exe` for `python` when running from the repository root. This runtime is local tooling and is not shipped in the application.

For a per-user Windows Docker Desktop installation, add its CLI and Git Bash to the current PowerShell session before running Make: `$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:ProgramFiles\Git\bin;" + $env:PATH`. Docker Desktop must be running.

Run backend tests with `python -m pytest backend/tests -q`; run `npm test` and `npm run build` inside `frontend`. If the Windows default temporary directory is restricted, add `--basetemp=.tools/pytest` to pytest. The frontend test runner disables Node's experimental browser storage so jsdom supplies real browser-compatible storage, including on Node 26.

## API

`POST /verify/pan` takes JSON `{"pan":"ABCPE1234F"}` and the `Idempotency-Key` header. PAN input is uppercased, then validated before any database lookup. Whitespace is rejected. Results are independent of the provider selected.

| HTTP | Outcome | Error code | Billed |
| --- | --- | --- | --- |
| 200 | Found | `null` | true |
| 200 | Not found | `IDTO_202` | true |
| 400 | Missing key | `IDTO_001` | false |
| 400 | Key contains a PAN or exceeds 128 characters | `IDTO_003` | false |
| 422 | Invalid PAN or JSON body | `IDTO_002` | false |
| 409 | Key belongs to another PAN | `IDTO_011` | false |
| 409 | Existing work exceeds this request's deadline | `IDTO_010` | false |
| 503 | Providers unavailable, or storage busy | `IDTO_008` | false |

Found: `{"status":"success","error_code":null,"data":{"pan":"ABCPE****F","name":"RAHUL SHARMA"},"billed":true}`.

Not found: `{"status":"success","error_code":"IDTO_202","data":null,"billed":true}`.

Errors use `{"status":"error","error_code":"...","message":"...","billed":false}` with the exact messages from the source PDF for `IDTO_001`, `IDTO_002`, `IDTO_010` and `IDTO_011`. No provider identity or unmasked PAN is returned. A done key replays the stored UTF-8 response bytes. Both successful outcomes use the same billing helper and create one 200-paise ledger row; failed work releases the key for a new attempt.

`GET /charges` returns `charges`, `amount_paise` and persistent `vendor_calls`. `GET /reconcile` compares both directions of the response/ledger relationship in one read snapshot. `GET /health` returns `{"status":"ok"}`. These endpoints have no `/api` prefix on the direct backend port.

## SQLite and recovery

Both replicas mount the same local Docker volume at `/data`. SQLite WAL provides concurrency; each process serializes database work on one dedicated thread with a persistent connection. Vendor waits use `asyncio.sleep` and do not occupy that database thread or block the event loop. Transactions use `BEGIN IMMEDIATE`, and every mutation checks the owner's random token. A unique ledger key and the final response transaction enforce one charge per key across replicas. The associated PAN is stored as a SHA-256 fingerprint of the normalized value, not as the full input. Final responses contain only the masked PAN.

Within a process, identical requests share an active task and its completed successful response for 100 ms. This reduces repeated database reads during duplicate bursts. Different PANs still go through SQLite conflict checks, and other replicas still acquire ownership through SQLite. Failed tasks are removed immediately and their waiters restart the lookup. Cancellation of a waiting HTTP request does not cancel the owner task. Disabling this optimization would retain the database's idempotency and billing guarantees.

Requests younger than 10 seconds wait and poll the persistent record. Requests older than 10 seconds can be reclaimed with a new owner token. A saved raw response survives reclamation and avoids another provider call. Vendor calls have a two-second cap and share the three-second deadline measured at ASGI request arrival. Provider attempt counters commit before the call; both timeouts and exceptions count. Storage contention returns an actionable 503 without exposing the database exception.

WAL uses `synchronous=NORMAL`: committed transactions survive process termination, including the required crash injection. Power loss may discard recent transactions, although SQLite preserves transaction consistency. The deployment assumes one host with a local filesystem supporting SQLite locks, not a network filesystem or replicas on different hosts. Idempotency keys are limited to 128 characters and rejected if they contain a PAN, since keys are stored and shown by reconciliation.

## Configuration and samples

`make up` rebuilds and recreates changed services while preserving the named `database` volume. Use `PRIMARY=b FAULT_VENDORS=a,b make up` to change runtime configuration. An explicitly empty `FAULT_VENDORS` disables all faults. Keep Docker's `DATABASE_PATH` underneath `/data` so it remains on the persistent volume.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PATH` | `data/pan.sqlite3` locally, `/data/pan.sqlite3` in Docker | Persistent database file |
| `PRIMARY` | `a` | `a` or `b`; secondary is the other provider |
| `FAULT_VENDORS` | `a` | Empty, `a`, `b`, or `a,b` |
| `CRASH_POINT` | empty | `after_vendor_call` or `after_vendor_persist` |
| `IMAGE_TAG` | `local` | Compose image tag; use immutable release tags for rollback |
| `BACKEND_PORT` | `8001` | Published direct backend port |
| `GATEWAY_PORT` | `8080` | Published gateway port |

`ABCPE1234F` is found; `ABCPE0000F` is not found. On a fault-selected provider, `ABCPE9999F` sleeps five seconds and `ABCPE8888F` raises an exception. On other providers those two PANs are found. Ordinary calls take 50 ms. A valid not-found result never triggers failover.

## Validation and remaining publication steps

Validated with Docker Desktop's Linux/WSL2 backend on a two-CPU Windows host, using the production images and gateway:

- `make test` passed 34 backend pytest cases inside an isolated container, including recovery and disconnect handling with both primary settings, exact API error bodies, stale-owner fencing, ledger rollback and data/log masking. It also passed the 15 frontend cases below and cleaned up its containers and network.
- 15 frontend Vitest/Testing Library tests passed for validation, retry keys, double clicks during pending and already-completed responses, loading, results, bounded history and unavailable storage.
- `make up` built all images and started two healthy backend replicas plus a healthy gateway. Direct port 8001 and `/api/health` both returned the required health body.
- All eight combinations of primary and fault settings passed through the gateway. Each configuration change used `make up`; stored totals survived every recreation. Direct-backend replays matched gateway response bytes.
- Both Docker crash drills passed on port 8001 with an actual dropped connection, restart and 11-second wait. Each added exactly one charge. The pre-persist crash made two total attempts; the post-persist crash made one total attempt and reused the saved result. Reconciliation was empty and logs contained no full sample PANs.
- Headless Chrome passed production found and not-found flows through Nginx, keyboard submission with visible focus, double-click suppression, masked localStorage, desktop rendering and 360 px mobile rendering without horizontal overflow or browser errors. Placeholder text contrast measured 4.69:1 and the input border 3.70:1. Screenshots were inspected locally.
- Production JavaScript measured 48,884 bytes gzipped, approximately 47.74 KiB. `npm run build` prints the current exact measurement and rejects bundles at or above 200,000 bytes.
- `make load` passed against freshly built images with `PRIMARY=a`, `FAULT_VENDORS=` and `CRASH_POINT=`. It sent 500 concurrent requests and measured p50/p95/p99 of 221.61/306.85/325.66 ms, exactly 50 new charges, exactly 50 vendor attempts and empty reconciliation. The generator uses aiohttp and uvloop on Linux; it does not reduce concurrency, prewarm connections or relax the 400 ms assertion.
- A later managed Linux host with three CPUs showed variable load latency: gateway p95 was 519.95 ms on its first batch, then 334.08 and 312.96 ms, and a later `make load` batch measured 663.99 ms. Every batch still produced exactly 50 charges, 50 attempts and empty reconciliation. The 400 ms gate therefore needs measurement on the target host under its expected load.
- The backend image measured 242,056,977 bytes on Docker Desktop and 166,502,217 bytes on the managed Linux host, both below 250,000,000 bytes, and runs as user `app`. The final gateway image contains no Node executable. Nginx configuration validation passed.

The CI build paths were checked locally and the workflow runs the same Make targets, checks image size and runtime contents, caches Docker dependency layers and uploads load-test JSON. The repository is [Pan-Verification-System](https://github.com/Nikhil-X-codes/Pan-Verification-System), with separate feature commits for the backend, frontend, Docker deployment, CI and operating documentation. This documentation records local validation, not a hosted CI result. Verify the GitHub Actions run before submission. The assignment email remains a separate owner action.

## Assumptions

1. The PDF says `billed` is true only when the current request creates a charge, but also requires byte-identical replay of a billed response. Byte-identical replay takes precedence: `billed:true` describes the original verification's charge and does not mean the retry created another charge.
2. The backend needs to associate each key with its normalized PAN, while the automatic-failure rule forbids full PANs in storage. Store a SHA-256 fingerprint for equality checks and only a masked PAN in the response. The full input is confined to the live request and fake-provider call.
3. Only four sample PAN records are supplied. Other syntactically valid PANs return not found; no additional fictional identities are introduced.
4. The response deadline caps provider work and waiting. Small response serialization and database completion overhead may extend wall-clock delivery slightly beyond three seconds; client connection queues are outside the ASGI arrival deadline.
5. An interrupted process can die between incrementing the persistent attempt counter and entering the provider coroutine. The counter means attempts initiated, not proof that a remote service received a packet. Providers are local fakes in this assignment.
6. Browser attempt keys stay in memory. The requirements specify reuse on retries but do not require persisting pending keys across tab closure. Reloading or reopening starts a new attempt; this limitation is explained below rather than storing unmasked PANs.
7. A network failure provides no authoritative `billed` value. The UI says the result is unknown and shows a retry, withholding a charging label until it receives the API value.
8. Storage failures are not listed separately in the response matrix. They use 503 `IDTO_008` with a storage-specific retry message so raw SQL exceptions never reach clients.
9. The load target depends on deployment hardware and competing work. The test enforces it without relaxing the threshold; run it on an otherwise idle stack with normal vendors.
10. Negative validation tests alter the supplied sample's format or holder letter. These are malformed inputs needed to test the guard, not additional identity records.

## Required design answers

### Crash windows

Before the claim commits, no work exists and a retry claims normally.<br>
After claim or attempt-count commit, a stale retry takes over and may call a provider again; no charge exists.<br>
After the provider answers but before raw persistence, the answer is lost and recovery calls again.<br>
After raw persistence, recovery reuses the saved answer without a new provider call.<br>
During final response/ledger commit SQLite rolls back or commits both; after commit, even a lost HTTP response is replayed without another charge.

### Simultaneous requests

SQLite serializes competing claims and stores a single owner token for each key.<br>
A fresh owner makes other requests wait; stale takeover replaces the token and fences the old owner.<br>
The response, done state and unique ledger key commit together, so replay cannot add a charge.<br>
The guarantee relies on a shared correctly locking SQLite file and keeping that file intact; separate databases or deleted volumes break it.

### A closed browser tab

Closing a tab can leave server work running; it can commit even when the browser never sees the response.<br>
Within the open page, network failures and manual or automatic retries reuse the same UUID and replay safely.<br>
After closure, the pending key is lost; returning and verifying again creates a new billable attempt.<br>
Masked history contains completed checks only; durable pending-key recovery is an explicit limitation of this implementation.

### Intentionally omitted

Real PAN integrations are intentionally omitted because this assignment requires deterministic fake providers.<br>
Only the supplied sample identity appears in successful results, with no external personal-data requests.<br>
This keeps timeout, failure, billing and crash behavior reproducible without credentials or paid services.
