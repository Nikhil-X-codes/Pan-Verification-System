import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def running(path, primary="a", faults="", crash=""):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_PATH": str(path), "PRIMARY": primary, "FAULT_VENDORS": faults, "CRASH_POINT": crash}
    log = open(path.parent / f"server-{port}.log", "w+")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=ROOT, env=env, stdout=log, stderr=log)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=8, trust_env=False)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(log.read())
            try:
                if client.get("/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.03)
        else:
            raise RuntimeError("Server startup timed out")
        yield client, process
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.seek(0)
        output = log.read()
        log.close()
        assert all(pan not in output for pan in ("ABCPE1234F", "ABCPE0000F", "ABCPE9999F", "ABCPE8888F"))


@pytest.fixture(params=["a", "b"])
def service(tmp_path, request):
    with running(tmp_path / "test.sqlite3", primary=request.param) as (client, process):
        yield client
