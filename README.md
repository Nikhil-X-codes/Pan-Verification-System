# PAN Verification System

Delivery milestone 4 of 5: backend, frontend, Docker deployment and GitHub Actions. Feature commits are published at least four hours apart. See [PUBLISHING.md](PUBLISHING.md) for commit guidelines and scheduling conditions.

## Run

1. Start Docker Desktop or Docker Engine, with Compose v2, GNU Make and Bash on PATH.
2. Run `make up` and open `http://localhost:8080`.
3. Run `make test` for isolated backend and frontend tests.
4. Run `FAULT_VENDORS= CRASH_POINT= make up`, then `make load` on an idle stack.
5. Run `make down` to stop without deleting persistent data.

The gateway serves React and balances `/api/` across two FastAPI replicas sharing persistent SQLite. Local validation passed 34 backend cases, 15 frontend cases, all eight provider configurations, both Docker crash drills and desktop/mobile Chrome checks. Local load p95 was 306.85 ms, with exactly 50 new charges and 50 vendor attempts and empty reconciliation.

## CI

The workflow runs on pull requests and pushes to `main`. It runs `make test`, builds images with cached dependencies, starts the production stack, checks backend image size and runtime contents, runs the gateway load test and uploads its JSON artifact. Failed assertions fail the job.

Check [GitHub Actions](https://github.com/Nikhil-X-codes/Pan-Verification-System/actions) for the actual hosted result. The local results above do not establish that CI passed.

The full operating guide, complete README and acceptance work plan are reserved for the fifth and final publishing batch.
