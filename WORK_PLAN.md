# IDTO Full-Stack Intern Assignment: Implementation Work Plan

## Implementation update, 2026-11-13

Local implementation and acceptance are complete: `make up`, 34 backend tests and 15 frontend tests through `make test`, all eight primary/fault configurations, both Docker crash drills, and production Chrome checks at desktop and 360 px widths passed. `make load` against the gateway passed with p95 306.85 ms, exactly 50 charges and 50 attempts, and empty reconciliation. The non-root backend image is 242,056,977 bytes; the gateway contains no Node executable. The GitHub repository is `Nikhil-X-codes/Pan-Verification-System`; the backend is published. The latest delivery plan has five commits: backend, frontend, Docker, CI, and final operating/acceptance documentation. The remaining four commits are published separately, at least four hours after each previous successful push. This replaces the earlier three-batch plan and two-hour interval. See `PUBLISHING.md` for commit guidelines and the local publisher's operating conditions. Hosted CI verification and email submission remain pending. These statuses describe the state when this plan was prepared; CI checkboxes remain open until a hosted run is verified.

## Purpose and source

This document converts the supplied 11-page **Full-Stack Intern Home Assignment: PAN Verification: Backend, Frontend and Deployment** into a build and verification checklist. The assignment PDF is the source of truth. This file is a **work plan**, not a substitute for the required `README.md` and `RUNBOOK.md` in the final repository.

**Estimated work:** 20 to 28 hours. **Due:** 2 days after receiving the assignment. **Passing score:** at least 75/100, provided no automatic-failure condition is triggered.

## 1. Delivery definition

Build a working web application that accepts a PAN, validates it, gets an answer from fake Vendor A or Vendor B, handles vendor failure and process crashes, records each billable verification exactly once, and shows the result in a React page. Run it through an Nginx gateway with two backend replicas and persistent storage. Supply tests, a load test, CI, operational instructions, and an understandable commit history.

### Required repository structure

```text
backend/                    FastAPI service, backend tests, loadtest.py
frontend/                   React 18, TypeScript strict mode, Vite, frontend tests
deploy/                     Dockerfiles, docker-compose.yml, Nginx gateway config
.github/workflows/ci.yml    GitHub Actions workflow
Makefile
.env.example
README.md
RUNBOOK.md
```

The implementation may contain additional needed files, but all paths above are mandatory.

## 2. Work sequence and acceptance checklist

### Phase A: Repository and setup

- [x] Create a GitHub repository with multiple meaningful commits rather than one large commit.
- [x] Create the mandatory directories and root files.
- [x] Use Python 3.11+, FastAPI, React 18, TypeScript strict mode, Vite, Docker, Nginx and GitHub Actions.
- [x] Choose persistent SQLite-file storage or PostgreSQL. In-memory-only storage is prohibited.
- [x] Define environment variables, documented defaults and `.env.example`, with no committed secrets.
- [x] Implement the `Makefile` contract precisely:
  - `make up`: build images, start services, expose gateway at `http://localhost:8080`.
  - `make test`: start all dependencies required by tests, run backend pytest and frontend Vitest, clean up.
  - `make load`: run `backend/loadtest.py` against the gateway from a running `make up`.
  - Running `make up` on an already running stack must recreate changed services while retaining stored data.
  - Support arguments such as `PRIMARY=b FAULT_VENDORS=a,b make up` and `CRASH_POINT= make up`.

### Phase B: Backend PAN validation and HTTP contract

- [x] Implement `POST /verify/pan`, `GET /charges`, `GET /reconcile`, `GET /health`.
- [x] Require `Idempotency-Key` on verification requests. If missing, return HTTP 400 and `IDTO_001`.
- [x] Immediately after checking the header, uppercase the submitted PAN and validate five letters, four digits, one letter, with the fourth letter one of `P C H F A T B L J G`.
- [x] Invalid input must return HTTP 422, `IDTO_002`; do not create an idempotency record, call a vendor, or charge.
- [x] Ensure the input guard occurs before idempotency lookup and all other processing after the header check.
- [x] Return the exact required JSON shape, status codes, error codes, message text where specified, and `billed` field:

| Case | HTTP | Error code | Billable |
| --- | ---: | --- | --- |
| Found PAN | 200 | `null` | Yes |
| Not found PAN | 200 | `IDTO_202` | Yes |
| Both vendors failed or timed out | 503 | `IDTO_008` | No |
| Missing key | 400 | `IDTO_001` | No |
| Invalid PAN | 422 | `IDTO_002` | No |
| Reused key, different PAN | 409 | `IDTO_011` | No |
| Still processing at deadline | 409 | `IDTO_010` | No |

- [x] For found results, return `{"status":"success","error_code":null,"data":{"pan":"ABCPE****F","name":"RAHUL SHARMA"},"billed":true}`.
- [x] For not found, return `{"status":"success","error_code":"IDTO_202","data":null,"billed":true}`.
- [x] Use the specific exact error messages given in the PDF for missing key, invalid PAN, key conflict, and still-processing key. For vendor failures use a specific actionable message, never raw exception text or vague messages.
- [x] Mask the PAN in every API response and every log line: first 5 characters, `****`, last character. Never include a vendor name in an API response.
- [x] Make a single helper responsible for computing `billed`, used on every response path. Found and not found are both successful and billed; consumers distinguish them by `error_code`, not `status`.
- [x] Make normalized responses independent of which vendor answers.

### Phase C: Fake vendors, deadlines and failover

- [x] Implement two plain Python classes named Vendor A and Vendor B in code and documentation.
- [x] Vendor A success format: `{"pan_status":"VALID","full_name":"RAHUL SHARMA"}`. Not found: `{"pan_status":"NOT_FOUND"}`.
- [x] Vendor B success format: `{"result":{"valid":true,"name":"RAHUL SHARMA"}}`. Not found: `{"result":{"valid":false}}`.
- [x] Simulate normal call latency of 50 ms; vendor calls must not block the event loop.
- [x] Read `PRIMARY=a|b` (default `a`); call primary first and use the other vendor as secondary.
- [x] Read `FAULT_VENDORS=a`, `b`, `a,b` or empty (default `a`). Empty means no faults.
- [x] Use only the assignment's sample PANs:

| PAN | On a vendor selected in `FAULT_VENDORS` | On any other vendor |
| --- | --- | --- |
| `ABCPE1234F` | Found: RAHUL SHARMA | Same |
| `ABCPE0000F` | Not found | Same |
| `ABCPE9999F` | Sleep 5 seconds | Found, like `ABCPE1234F` |
| `ABCPE8888F` | Raise an exception | Found, like `ABCPE1234F` |

- [x] Fail over only on an exception or timeout. Not found is a valid vendor answer, never a failover trigger.
- [x] Enforce 2 seconds maximum per vendor call and a 3-second total request deadline from arrival.
- [x] Return 503 `IDTO_008` if both vendors fail or time out.
- [x] Count **every** vendor attempt, including failures, timeouts and failovers, in persistent storage.

### Phase D: Idempotency, ledger and recovery

- [x] Persist each idempotency key, associated normalized PAN, state, and raw vendor response when available.
- [x] If a key is **done** with the same PAN, replay the original stored HTTP response byte-for-byte. Do not call vendors or charge again.
- [x] If a key is **done** with a different PAN, return 409 `IDTO_011`.
- [x] If a key is **in progress** and younger than 10 seconds, wait until it finishes, subject to the original 3-second request deadline. Return the final response when done, or 409 `IDTO_010` at deadline.
- [x] If the owner releases a failed key while another request waits, let the waiter begin again at the lookup step.
- [x] If a key remains in progress for more than 10 seconds, allow a safe takeover and completion.
- [x] Create an `in_progress` record before vendor work and save the raw vendor result on that record after an answer arrives.
- [x] In **one database transaction**, save the final response, create one 200-paise ledger charge for billable outcomes, and mark the idempotency key `done`.
- [x] If both vendors fail, do not store a final result and release the key so retrying the same key calls vendors anew.
- [x] Implement database constraints and concurrency control that prevent duplicate charges across both backend replicas, stale takeovers and crashes.
- [x] Implement `GET /charges` with stored values shaped as `{"charges":n,"amount_paise":n*200,"vendor_calls":m}`. Both replicas must return the same values.
- [x] Implement `GET /reconcile` with two arrays: `charges_without_response` and `billed_responses_without_charge`. Each entry is an idempotency key; both arrays must be empty whenever requests are no longer mid-flight, including after recovery.
- [x] Implement `GET /health` returning HTTP 200 and `{"status":"ok"}` for container healthchecks.

### Phase E: Crash injection and correctness

- [x] Read `CRASH_POINT=after_vendor_call|after_vendor_persist` (off by default).
- [x] At `after_vendor_call`, force `os._exit(1)` after vendor answer but before saving it.
- [x] At `after_vendor_persist`, force `os._exit(1)` after saving raw vendor answer but before final response and ledger transaction.
- [x] Publish `backend1` directly at `http://localhost:8001` with no `/api` prefix for crash testing.
- [x] For both crash points: start with the crash setting, send one request for `ABCPE1234F` against port 8001, observe dropped connection, restart with `CRASH_POINT` unset, wait 11 seconds, retry with the same key and confirm exactly one new charge.
- [x] For `after_vendor_persist`, confirm the retry makes **no new vendor call**.
- [x] Confirm `/reconcile` is empty once recovery completes.

### Phase F: Frontend

- [x] Build `/` with one labelled PAN input and a Verify button. Call only backend endpoints under `/api`; never contact vendors or compute billing in the browser.
- [x] Show live validation, including format and fourth-character holder type, with the specific reason displayed beneath the field.
- [x] Disable Verify when invalid or a verification is running.
- [x] Generate a new UUID idempotency key for each new attempt; use the same key on retries of that attempt.
- [x] Changing the PAN after a failure starts a new attempt and key. Double-clicks must not create two different keys or two requests.
- [x] Render all required states with clear copy:
  - Submitting: spinner; after 1.5 seconds also show `Still checking, this can take a few seconds`.
  - Found: masked PAN, name, and `Charged`/`Not charged`.
  - Not found: clear absence message and charging label.
  - HTTP 503: API-provided actionable message and Retry using same key.
  - HTTP 409 `IDTO_010`: auto-retry up to 3 times, 1 second apart with same key; then provide manual Retry.
  - Network failure: message distinct from server failure and Retry using same key.
- [x] Decide the charging label from API `billed` only. Never infer from status and never display a billing amount.
- [x] Store only last 20 verification history entries in `localStorage`, newest first, including masked PAN, outcome, and time. Never store a full PAN in storage, URL or console.
- [x] Gracefully handle localStorage being unavailable or blocked.
- [x] Meet accessibility requirements: labelled field, `aria-live` result announcements, keyboard access, visible focus and WCAG AA contrast.
- [x] Work at viewport widths down to 360 px without horizontal scroll.
- [x] Keep generated JavaScript below 200 KB gzipped; measure and report actual size in README.
- [x] Enable TypeScript strict mode. Do not use `any` or `// @ts-ignore`.

### Phase G: Deployment and gateway

- [x] Create `deploy/docker-compose.yml` with persistent storage, `backend1`, `backend2` and Nginx gateway.
- [x] Nginx serves the production frontend build and balances `/api/` traffic across both backend replicas.
- [x] Strip `/api` before forwarding. Example: gateway `POST http://localhost:8080/api/verify/pan` reaches backend `POST /verify/pan`.
- [x] Expose gateway on host port 8080 and `backend1` directly on port 8001.
- [x] Use a multi-stage backend image, non-root runtime user and final backend image below 250 MB.
- [x] Build frontend in a Docker stage; do not include Node in the final serving image.
- [x] Use environment configuration rather than hardcoded runtime settings; propagate the documented variables to both backends.
- [x] Use healthchecks, not time-based sleeps, for startup ordering.
- [x] Keep persistent database data intact when `make up` recreates changed services.

### Phase H: Automated testing

**Backend tests using real HTTP, both `PRIMARY` values:**

- [x] All required response rows and exact shapes.
- [x] Header missing, invalid PAN guards, fourth-letter validation and no side effects on invalid input.
- [x] Vendor success, not found, exception, timeout, failover and both-vendor failure.
- [x] Replay with byte-for-byte identical response and no second charge/vendor call.
- [x] Different PAN with reused key conflict.
- [x] Parallel identical requests, in-progress waiting, 10-second stale takeover, failed-key release.
- [x] Both crash points, recovery, persisted raw response reuse, reconciliation.
- [x] Full PAN never appears in logs; vendor-agnostic identical response bodies.
- [x] Each vendor call respects its timeout and does not block the event loop; total deadline enforced.

**Frontend tests using Vitest and Testing Library, at least 8 tests:**

- [x] Format and holder-type error copy.
- [x] One UUID key per attempt; retry retains same key.
- [x] Changing PAN after failure generates new key.
- [x] Double-click sends one request.
- [x] Each user-visible result/loading/error state.
- [x] `IDTO_010` auto-retry stops after three retries.
- [x] LocalStorage does not get full PAN; blocked storage does not crash.

**Load test:**

- [x] Implement `backend/loadtest.py` using the gateway. Send **500 concurrent requests** for `ABCPE1234F`: 50 new random keys per run, each submitted 10 times.
- [x] Read `/charges` before and after; require `charges_delta == 50`, `vendor_calls_delta == 50`, and empty `/reconcile`.
- [x] Report final output line as JSON with exactly the required fields: `p50_ms`, `p95_ms`, `p99_ms`, `charges_delta`, `vendor_calls_delta`, `reconcile_empty`.
- [x] Target `p95_ms < 400` with normal vendors; configure faults off for this performance case as needed, recording the setting.
- [x] Exit non-zero on any assertion failure.

### Phase I: CI, README and runbook

**GitHub Actions, `.github/workflows/ci.yml`:**

- [ ] Run on every pull request.
- [ ] Run `make test`.
- [ ] Build all images, start Docker Compose stack, then run `make load` against it.
- [ ] Fail workflow on non-zero exit; cache dependencies.
- [ ] Upload load test JSON as a CI artifact.

**README.md:**

- [x] Setup section in 10 lines or fewer.
- [x] `Assumptions` section listing **every** unclear, missing or contradictory requirement, each with a decision and reason. Record actual decisions made while implementing; do not invent ambiguities merely to populate the section.
- [x] Report the measured gzipped JavaScript bundle size.
- [x] Answer each of the following in **3 to 6 lines**, in your own words:
  1. Every crash window from request arrival to response, leftover state, and recovery behavior.
  2. What prevents double charging for simultaneous same-key requests, and where that guarantee could fail.
  3. What happens when a browser tab closes mid-request and the user returns; how key handling makes it safe.
  4. One thing intentionally not built and why.

**RUNBOOK.md:**

- [x] Keep to one page.
- [x] Explain how to start and stop services.
- [x] Explain how to roll back one bad deployment.
- [x] Define two monitoring alerts, each with threshold and reason.

## 3. Unbreakable project-wide rules

- [x] **No comments** in code, configuration or scripts.
- [x] **No em dash character** anywhere, including README and UI copy.
- [x] Keep solution minimal and fully functional; avoid single-use abstractions and unused settings.
- [x] Use **only** sample data provided in the assignment. Do not use real personal information.
- [x] Call the fake providers **Vendor A** and **Vendor B** in code and documentation; do not reveal names in API responses or UI.
- [x] Do not include an LLM or AI library in the shipped product. AI-assisted authoring is permitted, but the developer must understand every line.
- [x] No secrets, tokens or passwords committed.

## 4. Critical automatic-failure checks

All must be **false** before submitting:

- [ ] A double charge is possible in any crash or concurrency window.
- [ ] Idempotency depends on in-memory-only storage.
- [ ] A full PAN appears in stored history, logs or any URL.

Additional automatic deductions described by the assignment: comments in code (-3), em dashes (-2), real personal data (-5), and committed secrets (-5).

## 5. Final manual acceptance run

1. Configure a clean environment and run `make up`.
2. Confirm `http://localhost:8080/` loads and `http://localhost:8080/api/health` returns `{"status":"ok"}`.
3. Confirm direct `http://localhost:8001/health` works.
4. Run `make test`; ensure pytest and Vitest both pass and test-managed services are cleaned up.
5. With normal vendor conditions, run `make load` on the running stack; inspect the final JSON and assert charge delta 50, vendor calls delta 50, empty reconciliation, and p95 target.
6. Verify both PRIMARY configurations and `FAULT_VENDORS` cases.
7. Test both forced-crash points by contacting port 8001 and using the exact recovery sequence.
8. Check logs, browser storage, and URL behavior for PAN leakage.
9. Inspect image size, frontend gzipped JavaScript size, accessibility and responsive layout.
10. Inspect CI runs, README, RUNBOOK, `.env.example`, commit history and repository visibility/access.
11. Reply to the email that supplied the assignment with the GitHub repository URL (public, or private with access shared).

## 6. Work tracking by suggested milestone

| Milestone | Deliverable | Done when |
| --- | --- | --- |
| 1 | Backend core | Guard, response contract, fake vendors and basic tests pass |
| 2 | Idempotency and ledger | Concurrent retries cannot double charge; reconciliation correct |
| 3 | React verify page | All required states, storage and tests work |
| 4 | Containers and gateway | Gateway serves frontend, routes API and balances replicas |
| 5 | Failover and crash recovery | Timeout, exception and both crash sequences pass |
| 6 | CI and documentation | Workflow, load test, README and RUNBOOK pass review |

This milestone order follows the build order recommended on page 11 of the assignment. Do not mark any item complete until it is implemented and verified.
