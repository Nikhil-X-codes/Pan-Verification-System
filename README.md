# PAN Verification System

Delivery milestone 3 of 5: the SQLite-backed FastAPI service, React verification page and complete Docker deployment. Source is published at least four hours apart. See [PUBLISHING.md](PUBLISHING.md) for commit and timing guidelines.

## Run the stack

1. Start Docker Desktop or Docker Engine, with Compose v2, GNU Make and Bash on PATH.
2. Copy `.env.example` to `.env` if defaults need changing.
3. Run `make up` and open `http://localhost:8080`.
4. Direct backend health is `http://localhost:8001/health`.
5. Run `make test` for isolated backend and frontend tests, with cleanup.
6. Run `FAULT_VENDORS= CRASH_POINT= make up`, then `make load` on an idle stack.
7. Run `make down` to stop while retaining the database volume.

The gateway serves the production React build and balances `/api/` across two non-root backend replicas. Both mount one persistent SQLite volume. All eight primary/fault settings and both Docker crash drills passed locally. The backend image measured 242,056,977 bytes. The gateway contains no Node executable.

The local test run passed 34 backend cases and 15 frontend cases. The 500-request gateway load test measured p95 306.85 ms with exactly 50 new charges, 50 vendor attempts and empty reconciliation. These are local results, not a hosted CI claim.

GitHub Actions arrives in batch 4. The final operating guide, full README and acceptance work plan follow in batch 5.
