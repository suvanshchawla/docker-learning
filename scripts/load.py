"""Tiny HTTP load generator (standard library only).

usage: load.py URL TOTAL_REQUESTS CONCURRENCY COMPOSE_PROJECT

Sends TOTAL_REQUESTS GET requests from CONCURRENCY threads and prints a JSON
summary. While it runs it samples pg_stat_activity in the given Compose
project's postgres container to record the most connections it saw.
"""
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

url, total, concurrency, project = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]

PSQL = (
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc '
    '"select count(*) from pg_stat_activity '
    'where datname = current_database() and pid <> pg_backend_pid()"'
)

latencies, errors = [], 0
sent = 0
max_conns = 0
lock = threading.Lock()
done = threading.Event()


def sample_connections():
    global max_conns
    cmd = ["docker", "compose", "-p", project, "exec", "-T", "postgres", "sh", "-c", PSQL]
    while not done.is_set():
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
            max_conns = max(max_conns, int(out or 0))
        except Exception:
            pass


def worker():
    global sent, errors
    while True:
        with lock:
            if sent >= total:
                return
            sent += 1
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                resp.read()
                ok = resp.status == 200
        except Exception:
            ok = False
        elapsed = time.perf_counter() - started
        with lock:
            latencies.append(elapsed)
            if not ok:
                errors += 1


threading.Thread(target=sample_connections, daemon=True).start()
begin = time.perf_counter()
threads = [threading.Thread(target=worker) for _ in range(concurrency)]
for t in threads:
    t.start()
for t in threads:
    t.join()
wall = time.perf_counter() - begin
done.set()

latencies.sort()
print(json.dumps({
    "req_per_sec": round(total / wall, 1),
    "p50_ms": round(statistics.median(latencies) * 1000, 1),
    "p95_ms": round(latencies[int(len(latencies) * 0.95)] * 1000, 1),
    "errors": errors,
    "max_db_conns_seen": max_conns,
}))
