# IDTO operations

## Start and stop

Run `make up`, then check `http://localhost:8080/api/health` and `http://localhost:8001/health`. The page is at `http://localhost:8080`. Run `make down` to stop. Never add `--volumes` to the production down command: `/data` holds idempotency, ledger and attempt counters. `docker compose -f deploy/docker-compose.yml logs --tail=100` shows lifecycle and errors without access logs.

## Configure and roll back

Use `PRIMARY=b FAULT_VENDORS= CRASH_POINT= make up` for a healthy-provider configuration. For a release, build and retain images tagged with its immutable release ID using `IMAGE_TAG=<release> make up`. Preserve the prior backend and gateway image tags. Roll back using `IMAGE_TAG=<previous-release> docker compose -f deploy/docker-compose.yml up -d --no-build --wait`. Keep the same volume, check both health URLs and `/api/reconcile`, then verify a sample with a fresh key. The initial schema has no migrations; review database compatibility before later schema changes.

## Crash recovery drill

Record `/api/charges`, then run `CRASH_POINT=after_vendor_call make up`. POST `{"pan":"ABCPE1234F"}` to `http://localhost:8001/verify/pan` with `Content-Type: application/json` and an `Idempotency-Key` unique to the drill. Expect a dropped connection. Run `CRASH_POINT= make up`, wait 11 seconds, and retry the exact body and key. Expect one new charge; `/api/reconcile` must contain two empty arrays. Repeat with `after_vendor_persist` and another key. The persisted-answer retry must add zero provider calls; the first crash point normally adds one. Never run the load test with crash injection enabled.

## Monitoring alerts

1. Page if either reconciliation array stays nonempty for two consecutive one-minute checks. Response and ledger must commit together; a persistent mismatch indicates corruption or a broken write path.
2. Alert if verification 5xx rate exceeds 5% over five minutes with at least 20 requests, or a health probe fails three times at ten-second intervals. This detects provider outages, storage contention and dead containers. Collect response-code metrics at the probe/client layer without recording PANs or request bodies.

## Acceptance

Run `make test`, then `FAULT_VENDORS= CRASH_POINT= make up` and `make load` on an idle stack. Require exactly 50 new charges, exactly 50 attempts, empty reconciliation and p95 below 400 ms. Inspect size with `docker image inspect idto-backend:local --format '{{.Size}}'`; require less than 250,000,000 bytes. Local Docker configuration and crash drills passed; the measured image was 242,056,977 bytes and gateway load p95 was 306.85 ms. Repeat acceptance on the target host. Verify the hosted GitHub Actions run after the CI batch publishes. The assignment email remains a separate owner action.
