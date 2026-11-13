import asyncio
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Storage:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlite")
        self.connection = sqlite3.connect(path, timeout=0.1, isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    key TEXT PRIMARY KEY,
                    pan TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('in_progress','done')),
                    owner TEXT NOT NULL,
                    started REAL NOT NULL,
                    raw TEXT,
                    response TEXT,
                    http_status INTEGER,
                    billed INTEGER NOT NULL DEFAULT 0 CHECK(billed IN (0,1)),
                    CHECK(state != 'done' OR (response IS NOT NULL AND http_status IS NOT NULL))
                );
                CREATE TABLE IF NOT EXISTS ledger (
                    key TEXT PRIMARY KEY REFERENCES requests(key),
                    amount_paise INTEGER NOT NULL CHECK(amount_paise = 200)
                );
                CREATE TABLE IF NOT EXISTS counters (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    vendor_calls INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO counters(id) VALUES (1);
            """)

    @contextmanager
    def connect(self):
        with self.lock:
            try:
                yield self.connection
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    async def run(self, method, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, method, *args)

    def close(self):
        self.executor.shutdown(wait=True)
        self.connection.close()

    def claim(self, key: str, pan: str) -> dict:
        pan = hashlib.sha256(pan.encode("ascii")).hexdigest()
        with self.connect() as db:
            row = db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
            if row and row["pan"] != pan:
                return {"kind": "conflict"}
            if row and row["state"] == "done":
                return {"kind": "done", "body": row["response"], "status": row["http_status"]}
            if row and time.time() - row["started"] <= 10:
                return {"kind": "wait"}
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
            if row and row["pan"] != pan:
                return {"kind": "conflict"}
            if row and row["state"] == "done":
                return {"kind": "done", "body": row["response"], "status": row["http_status"]}
            if row and time.time() - row["started"] <= 10:
                return {"kind": "wait"}
            owner = uuid.uuid4().hex
            if row:
                db.execute("UPDATE requests SET owner=?, started=? WHERE key=?", (owner, time.time(), key))
            else:
                db.execute(
                    "INSERT INTO requests(key,pan,state,owner,started) VALUES (?,?,'in_progress',?,?)",
                    (key, pan, owner, time.time()),
                )
            db.commit()
            return {"kind": "owned", "owner": owner, "raw": json.loads(row["raw"]) if row and row["raw"] else None}

    def attempt(self, key: str, owner: str) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owned = db.execute("SELECT 1 FROM requests WHERE key=? AND owner=? AND state='in_progress'", (key, owner)).fetchone()
            if not owned:
                return False
            db.execute("UPDATE counters SET vendor_calls=vendor_calls+1 WHERE id=1")
            db.commit()
            return True

    def persist(self, key: str, owner: str, raw: dict) -> bool:
        with self.connect() as db:
            return db.execute(
                "UPDATE requests SET raw=? WHERE key=? AND owner=? AND state='in_progress'",
                (json.dumps(raw), key, owner),
            ).rowcount == 1

    def finish(self, key: str, owner: str, body: str, billed: bool) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                "UPDATE requests SET state='done',response=?,http_status=200,billed=? WHERE key=? AND owner=? AND state='in_progress'",
                (body, int(billed), key, owner),
            ).rowcount
            if not updated:
                return False
            if billed:
                db.execute("INSERT INTO ledger(key,amount_paise) VALUES (?,200)", (key,))
            db.commit()
            return True

    def release(self, key: str, owner: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM requests WHERE key=? AND owner=? AND state='in_progress' AND raw IS NULL", (key, owner))

    def charges(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT (SELECT count(*) FROM ledger) AS charges, (SELECT coalesce(sum(amount_paise),0) FROM ledger) AS amount_paise, vendor_calls FROM counters WHERE id=1").fetchone()
            return dict(row)

    def reconcile(self) -> dict:
        with self.connect() as db:
            db.execute("BEGIN")
            missing_response = db.execute("SELECT l.key FROM ledger l LEFT JOIN requests r ON r.key=l.key WHERE r.response IS NULL OR r.state!='done' OR r.billed!=1 ORDER BY l.key").fetchall()
            missing_charge = db.execute("SELECT r.key FROM requests r LEFT JOIN ledger l ON l.key=r.key WHERE r.state='done' AND r.billed=1 AND l.key IS NULL ORDER BY r.key").fetchall()
            return {"charges_without_response": [r[0] for r in missing_response], "billed_responses_without_charge": [r[0] for r in missing_charge]}
