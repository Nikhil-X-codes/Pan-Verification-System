import asyncio
import json
import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .storage import Storage
from .vendors import VendorA, VendorB, normalize


class RequestDeadline:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["deadline"] = time.monotonic() + 3
        await self.app(scope, receive, send)


def is_billed(status: str, code: str | None) -> bool:
    return status == "success" and code in (None, "IDTO_202")


def encode(body: dict) -> str:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True)


def response(body: dict, status: int = 200) -> Response:
    body["billed"] = is_billed(body["status"], body["error_code"])
    return Response(encode(body), status_code=status, media_type="application/json")


def error(code: str, message: str, status: int) -> Response:
    return response({"status": "error", "error_code": code, "message": message}, status)


def mask(pan: str) -> str:
    return pan[:5] + "****" + pan[-1]


def create_app() -> FastAPI:
    primary = os.getenv("PRIMARY", "a").lower()
    faults = set(filter(None, os.getenv("FAULT_VENDORS", "a").lower().split(",")))
    crash = os.getenv("CRASH_POINT", "")
    flights: dict[tuple[str, str], asyncio.Task[Response]] = {}
    if primary not in {"a", "b"} or not faults <= {"a", "b"} or crash not in {"", "after_vendor_call", "after_vendor_persist"}:
        raise ValueError("Invalid PRIMARY, FAULT_VENDORS or CRASH_POINT configuration")

    def discard(identity, finished):
        if flights.get(identity) is finished:
            flights.pop(identity, None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = await asyncio.to_thread(Storage, os.getenv("DATABASE_PATH", "data/pan.sqlite3"))
        yield
        if flights:
            await asyncio.gather(*tuple(flights.values()), return_exceptions=True)
        await asyncio.to_thread(app.state.storage.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(sqlite3.Error)
    async def database_unavailable(request: Request, exc: sqlite3.Error):
        return error("IDTO_008", "Verification storage could not complete this request. Retry with the same Idempotency-Key.", 503)

    app.add_middleware(RequestDeadline)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/charges")
    async def charges(request: Request):
        db = request.app.state.storage
        return await db.run(db.charges)

    @app.get("/reconcile")
    async def reconcile(request: Request):
        db = request.app.state.storage
        return await db.run(db.reconcile)

    @app.post("/verify/pan")
    async def verify(request: Request):
        key = request.headers.get("Idempotency-Key")
        if not key or not key.strip():
            return error("IDTO_001", "Idempotency-Key header is required.", 400)
        if len(key) > 128 or re.search(r"[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]", key, re.IGNORECASE):
            return error("IDTO_003", "Idempotency-Key must be at most 128 characters and contain no PAN.", 400)
        try:
            payload = await request.json()
            pan = payload.get("pan") if isinstance(payload, dict) else None
            pan = pan.upper() if isinstance(pan, str) else ""
        except (ValueError, UnicodeError):
            pan = ""
        if not re.fullmatch(r"[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]", pan):
            return error("IDTO_002", "PAN must be 5 letters, 4 digits, 1 letter, and the 4th letter must be one of P, C, H, F, A, T, B, L, J, G.", 422)
        identity = (key, pan)
        deadline = request.state.deadline
        while time.monotonic() < deadline:
            task = flights.get(identity)
            owner = task is None
            if task is None:
                task = asyncio.create_task(process(key, pan, deadline))
                flights[identity] = task

                def completed(finished, identity=identity):
                    if not finished.cancelled() and finished.exception() is None and finished.result().status_code == 200:
                        asyncio.get_running_loop().call_later(0.1, discard, identity, finished)
                    else:
                        discard(identity, finished)

                task.add_done_callback(completed)
            try:
                result = await asyncio.wait_for(asyncio.shield(task), max(0, deadline - time.monotonic() + (0.1 if owner else 0)))
            except TimeoutError:
                break
            if not owner and result.status_code == 503:
                if flights.get(identity) is task:
                    flights.pop(identity, None)
                continue
            return Response(result.body, status_code=result.status_code, media_type="application/json")
        return error("IDTO_010", "This request is still processing. Retry with the same Idempotency-Key.", 409)

    async def process(key: str, pan: str, deadline: float) -> Response:
        db = app.state.storage
        while time.monotonic() < deadline:
            claim = await db.run(db.claim, key, pan)
            if claim["kind"] == "conflict":
                return error("IDTO_011", "This Idempotency-Key was already used with a different PAN.", 409)
            if claim["kind"] == "done":
                return Response(claim["body"], status_code=claim["status"], media_type="application/json")
            if claim["kind"] == "wait":
                await asyncio.sleep(min(0.015, max(0, deadline - time.monotonic())))
                continue
            owner = claim["owner"]
            raw = claim["raw"]
            if raw is None:
                vendors = {"a": VendorA(), "b": VendorB()}
                for selected in (primary, "b" if primary == "a" else "a"):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    if not await db.run(db.attempt, key, owner):
                        break
                    try:
                        raw = await asyncio.wait_for(vendors[selected].verify(pan, selected in faults), timeout=min(2, max(0, deadline - time.monotonic())))
                        break
                    except (TimeoutError, RuntimeError):
                        continue
                if raw is None:
                    await db.run(db.release, key, owner)
                    return error("IDTO_008", "Both verification services failed or exceeded the request deadline. Retry with the same Idempotency-Key.", 503)
                if crash == "after_vendor_call":
                    os._exit(1)
                if not await db.run(db.persist, key, owner, raw):
                    continue
                if crash == "after_vendor_persist":
                    os._exit(1)
            found, name = normalize(raw)
            body = {"status": "success", "error_code": None if found else "IDTO_202", "data": {"pan": mask(pan), "name": name} if found else None}
            body["billed"] = is_billed(body["status"], body["error_code"])
            encoded = encode(body)
            if await db.run(db.finish, key, owner, encoded, body["billed"]):
                return Response(encoded, status_code=200, media_type="application/json")
        return error("IDTO_010", "This request is still processing. Retry with the same Idempotency-Key.", 409)

    return app


app = create_app()
