import asyncio
import hashlib
import sqlite3
import socket
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from conftest import running


FOUND = "ABCPE1234F"
NOT_FOUND = "ABCPE0000F"
EXPECTED = {"status": "success", "error_code": None, "data": {"pan": "ABCPE****F", "name": "RAHUL SHARMA"}, "billed": True}
EMPTY = {"charges_without_response": [], "billed_responses_without_charge": []}


def verify(client, key="one", pan=FOUND):
    return client.post("/verify/pan", headers={"Idempotency-Key": key}, json={"pan": pan})


def test_guards_have_no_side_effects(service):
    missing = service.post("/verify/pan", json={"pan": FOUND})
    assert missing.status_code == 400
    assert missing.json() == {"status": "error", "error_code": "IDTO_001", "message": "Idempotency-Key header is required.", "billed": False}
    assert service.post("/verify/pan", content="invalid").json()["error_code"] == "IDTO_001"
    for key in (FOUND, f"attempt-{FOUND.lower()}", "x" * 129):
        blocked = verify(service, key=key)
        assert blocked.status_code == 400
        assert blocked.json()["error_code"] == "IDTO_003"
        assert blocked.json()["billed"] is False
    for invalid in ("", "ABCXE1234F", "ABCPE123F", None, 123, "ABCPE１２３４F"):
        response = verify(service, pan=invalid)
        assert response.status_code == 422
        assert response.json()["error_code"] == "IDTO_002"
        assert response.json()["billed"] is False
        assert response.json() == {"status": "error", "error_code": "IDTO_002", "message": "PAN must be 5 letters, 4 digits, 1 letter, and the 4th letter must be one of P, C, H, F, A, T, B, L, J, G.", "billed": False}
    assert service.get("/charges").json() == {"charges": 0, "amount_paise": 0, "vendor_calls": 0}
    assert verify(service).json() == EXPECTED
    assert verify(service, pan="ABCXE1234F").status_code == 422


def test_success_replay_conflict_not_found(service):
    first = verify(service, pan=FOUND.lower())
    assert first.status_code == 200
    assert first.json() == EXPECTED
    assert verify(service).content == first.content
    conflict = verify(service, pan=NOT_FOUND)
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDTO_011"
    assert conflict.json()["billed"] is False
    assert conflict.json() == {"status": "error", "error_code": "IDTO_011", "message": "This Idempotency-Key was already used with a different PAN.", "billed": False}
    missing = verify(service, "missing", NOT_FOUND)
    assert missing.json() == {"status": "success", "error_code": "IDTO_202", "data": None, "billed": True}
    assert service.get("/charges").json() == {"charges": 2, "amount_paise": 400, "vendor_calls": 2}
    assert service.get("/reconcile").json() == EMPTY


def test_parallel_identical_requests(service):
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: verify(service), range(20)))
    assert all(r.json() == EXPECTED and r.status_code == 200 for r in responses)
    assert len({r.content for r in responses}) == 1
    assert service.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": 1}


@pytest.mark.parametrize("primary", ["a", "b"])
def test_not_found_never_fails_over(tmp_path, primary):
    with running(tmp_path / "db.sqlite3", primary, "a,b") as (client, _):
        result = verify(client, "missing", NOT_FOUND)
        assert result.status_code == 200
        assert result.json()["error_code"] == "IDTO_202"
        assert client.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": 1}


@pytest.mark.parametrize("primary", ["a", "b"])
@pytest.mark.parametrize("pan", ["ABCPE8888F", "ABCPE9999F"])
def test_failover_and_nonblocking_health(tmp_path, primary, pan):
    with running(tmp_path / "db.sqlite3", primary, primary) as (client, _):
        with ThreadPoolExecutor() as pool:
            start = time.monotonic()
            request = pool.submit(verify, client, "failover", pan)
            time.sleep(0.03)
            health_start = time.monotonic()
            assert client.get("/health").json() == {"status": "ok"}
            assert time.monotonic() - health_start < 0.5
            result = request.result()
        assert result.json() == EXPECTED
        elapsed = time.monotonic() - start
        assert elapsed < 3.3
        if pan == "ABCPE9999F":
            assert 2 <= elapsed < 2.8
        assert client.get("/charges").json()["vendor_calls"] == 2


@pytest.mark.parametrize("primary", ["a", "b"])
@pytest.mark.parametrize("pan", ["ABCPE8888F", "ABCPE9999F"])
def test_both_fail_release_key(tmp_path, primary, pan):
    with running(tmp_path / "db.sqlite3", primary, "a,b") as (client, _):
        for _ in range(2):
            start = time.monotonic()
            result = verify(client, pan=pan)
            assert result.status_code == 503
            assert result.json()["error_code"] == "IDTO_008"
            assert result.json()["billed"] is False
            assert time.monotonic() - start < 3.3
        assert client.get("/charges").json() == {"charges": 0, "amount_paise": 0, "vendor_calls": 4}
        assert client.get("/reconcile").json() == EMPTY


def seed(path, key, age, raw=None):
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO requests(key,pan,state,owner,started,raw) VALUES (?,?,'in_progress','dead-owner',?,?)", (key, hashlib.sha256(FOUND.encode("ascii")).hexdigest(), time.time() - age, raw))


@pytest.mark.parametrize("primary", ["a", "b"])
def test_in_progress_deadline_conflict_and_stale_takeover(tmp_path, primary):
    path = tmp_path / "db.sqlite3"
    with running(path, primary) as (client, _):
        seed(path, "busy", 0)
        start = time.monotonic()
        pending = verify(client, "busy")
        assert 2.9 <= time.monotonic() - start < 3.4
        assert pending.status_code == 409
        assert pending.json()["error_code"] == "IDTO_010"
        assert pending.json() == {"status": "error", "error_code": "IDTO_010", "message": "This request is still processing. Retry with the same Idempotency-Key.", "billed": False}
        assert verify(client, "busy", NOT_FOUND).json()["error_code"] == "IDTO_011"
        seed(path, "stale", 11)
        assert verify(client, "stale").json() == EXPECTED
        assert client.get("/charges").json()["charges"] == 1


def test_two_replicas_share_sqlite(tmp_path):
    path = tmp_path / "db.sqlite3"
    with running(path, "a") as (first, _), running(path, "b") as (second, _):
        with ThreadPoolExecutor(max_workers=20) as pool:
            responses = list(pool.map(lambda i: verify(first if i % 2 else second), range(40)))
        assert all(r.json() == EXPECTED for r in responses)
        assert first.get("/charges").json() == second.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": 1}
        assert second.get("/reconcile").json() == EMPTY


@pytest.mark.parametrize("point,expected_calls", [("after_vendor_call", 2), ("after_vendor_persist", 1)])
@pytest.mark.parametrize("primary", ["a", "b"])
def test_crash_recovery(tmp_path, point, expected_calls, primary):
    path = tmp_path / "db.sqlite3"
    with running(path, primary, crash=point) as (client, process):
        with pytest.raises(httpx.TransportError):
            verify(client, "crash")
        assert process.wait(timeout=5) == 1
    with running(path, primary) as (client, _):
        time.sleep(11)
        result = verify(client, "crash")
        assert result.json() == EXPECTED
        assert verify(client, "crash").content == result.content
        assert client.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": expected_calls}
        assert client.get("/reconcile").json() == EMPTY
    for log in tmp_path.glob("*.log"):
        assert FOUND not in log.read_text()


@pytest.mark.parametrize("primary", ["a", "b"])
def test_waiter_retries_after_failed_owner_releases(tmp_path, primary):
    path = tmp_path / "db.sqlite3"
    with running(path, primary) as (client, _):
        seed(path, "released", 0)
        with ThreadPoolExecutor() as pool:
            waiter = pool.submit(verify, client, "released")
            time.sleep(0.1)
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM requests WHERE key='released'")
            assert waiter.result().json() == EXPECTED
        assert client.get("/charges").json()["vendor_calls"] == 1


def test_old_owner_cannot_persist_or_finalize(tmp_path):
    import sys
    from conftest import ROOT
    sys.path.insert(0, str(ROOT))
    from app.storage import Storage
    db = Storage(str(tmp_path / "db.sqlite3"))
    old = db.claim("fenced", FOUND)
    with db.connect() as connection:
        connection.execute("UPDATE requests SET started=?", (time.time() - 11,))
    current = db.claim("fenced", FOUND)
    assert old["owner"] != current["owner"]
    assert db.attempt("fenced", old["owner"]) is False
    assert db.persist("fenced", old["owner"], {}) is False
    assert db.finish("fenced", old["owner"], "{}", True) is False
    db.release("fenced", old["owner"])
    assert db.claim("fenced", FOUND)["kind"] == "wait"
    assert db.charges()["charges"] == 0
    db.close()


@pytest.mark.parametrize("primary", ["a", "b"])
def test_final_transaction_rolls_back_on_ledger_failure(tmp_path, primary):
    path = tmp_path / "db.sqlite3"
    with running(path, primary) as (client, _):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TRIGGER fail_charge BEFORE INSERT ON ledger BEGIN SELECT RAISE(ABORT,'injected'); END")
        failed = verify(client, "atomic")
        assert failed.status_code == 503
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT state,response,raw FROM requests WHERE key='atomic'").fetchone()
            assert row[0] == "in_progress"
            assert row[1] is None
            assert row[2] is not None
            assert db.execute("SELECT count(*) FROM ledger").fetchone()[0] == 0
            db.execute("DROP TRIGGER fail_charge")
            db.execute("UPDATE requests SET started=? WHERE key='atomic'", (time.time() - 11,))
        assert verify(client, "atomic").json() == EXPECTED
        assert client.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": 1}
        assert client.get("/reconcile").json() == EMPTY


@pytest.mark.parametrize("primary", ["a", "b"])
def test_database_never_stores_full_pan(tmp_path, primary):
    path = tmp_path / "db.sqlite3"
    with running(path, primary) as (client, _):
        assert verify(client).json() == EXPECTED
        assert verify(client, "absent", NOT_FOUND).status_code == 200
        with sqlite3.connect(path) as db:
            dump = "\n".join(db.iterdump())
            assert FOUND not in dump
            assert NOT_FOUND not in dump
            assert "ABCPE****F" in dump


@pytest.mark.parametrize("primary", ["a", "b"])
def test_coalesced_waiter_restarts_after_owner_failure(tmp_path, primary):
    with running(tmp_path / "db.sqlite3", primary, "a,b") as (client, _):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(verify, client, "released", "ABCPE8888F")
            time.sleep(0.02)
            second = pool.submit(verify, client, "released", "ABCPE8888F")
            assert first.result().status_code == 503
            assert second.result().status_code == 503
        assert client.get("/charges").json() == {"charges": 0, "amount_paise": 0, "vendor_calls": 4}
        assert client.get("/reconcile").json() == EMPTY


@pytest.mark.parametrize("primary", ["a", "b"])
def test_disconnected_request_is_safely_replayed(tmp_path, primary):
    with running(tmp_path / "db.sqlite3", primary) as (client, _):
        body = b'{"pan":"ABCPE1234F"}'
        with socket.create_connection(("127.0.0.1", client.base_url.port)) as connection:
            headers = f"POST /verify/pan HTTP/1.1\r\nHost: localhost\r\nIdempotency-Key: disconnected\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
            connection.sendall(headers.encode("ascii") + body)
        time.sleep(0.2)
        assert verify(client, "disconnected").json() == EXPECTED
        assert client.get("/charges").json() == {"charges": 1, "amount_paise": 200, "vendor_calls": 1}
