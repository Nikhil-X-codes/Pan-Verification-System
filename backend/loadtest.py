import argparse
import asyncio
import json
import math
import sys
import time
import uuid

import aiohttp


async def run(base_url: str, output: str | None):
    connector = aiohttp.TCPConnector(limit=500)
    async with aiohttp.ClientSession(base_url=base_url.rstrip("/") + "/", connector=connector, timeout=aiohttp.ClientTimeout(total=15), trust_env=False) as client:
        async with client.get("charges") as before_response:
            before_response.raise_for_status()
            before = await before_response.json()
        gate = asyncio.Event()

        async def verify(key):
            await gate.wait()
            start = time.perf_counter()
            try:
                async with client.post("verify/pan", headers={"Idempotency-Key": key}, json={"pan": "ABCPE1234F"}) as result:
                    body = await result.json()
                    valid = result.status == 200 and body == {"status": "success", "error_code": None, "data": {"pan": "ABCPE****F", "name": "RAHUL SHARMA"}, "billed": True}
            except (aiohttp.ClientError, TimeoutError, ValueError):
                valid = False
            return (time.perf_counter() - start) * 1000, valid

        keys = [str(uuid.uuid4()) for _ in range(50)]
        tasks = [asyncio.create_task(verify(key)) for _ in range(10) for key in keys]
        gate.set()
        results = await asyncio.gather(*tasks)
        timings = sorted(elapsed for elapsed, valid in results)
        async with client.get("charges") as after_response:
            after_response.raise_for_status()
            after = await after_response.json()
        async with client.get("reconcile") as reconciliation:
            reconciliation.raise_for_status()
            data = await reconciliation.json()
        report = {
            "p50_ms": round(timings[math.ceil(len(timings) * 0.50) - 1], 2),
            "p95_ms": round(timings[math.ceil(len(timings) * 0.95) - 1], 2),
            "p99_ms": round(timings[math.ceil(len(timings) * 0.99) - 1], 2),
            "charges_delta": after["charges"] - before["charges"],
            "vendor_calls_delta": after["vendor_calls"] - before["vendor_calls"],
            "reconcile_empty": data == {"charges_without_response": [], "billed_responses_without_charge": []},
        }
        encoded = json.dumps(report)
        if output:
            with open(output, "w") as file:
                file.write(encoded + "\n")
        passed = True
        try:
            assert all(valid for elapsed, valid in results), "Expected 500 successful, normalized responses"
            assert report["charges_delta"] == 50, "Expected exactly 50 charges"
            assert report["vendor_calls_delta"] == 50, "Expected exactly 50 vendor attempts"
            assert report["reconcile_empty"], "Reconciliation found a mismatch"
            assert report["p95_ms"] < 400, "p95 exceeded the 400 ms target"
        except AssertionError as exc:
            print(f"Load test failed: {exc}", file=sys.stderr, flush=True)
            passed = False
        print(encoded, flush=True)
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080/api")
    parser.add_argument("--output")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.run(run(args.url, args.output))
    else:
        import uvloop
        uvloop.run(run(args.url, args.output))
