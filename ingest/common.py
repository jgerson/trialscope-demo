"""Helpers shared by the ingest scripts: resumable, concurrent batch upserts."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tp_client  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def load_batches(namespace: str, rows: list[dict], kind: str, batch_size: int = 200, workers: int = 4) -> None:
    """Upsert rows in batches, skipping batches already loaded in an earlier run."""
    state_path = os.path.join(DATA_DIR, f".loaded-{namespace}.json")
    done = set(json.load(open(state_path))) if os.path.exists(state_path) else set()
    batches = [(i, rows[i : i + batch_size]) for i in range(0, len(rows), batch_size)]
    todo = [(i, b) for i, b in batches if i not in done]
    print(f"{namespace}: {len(rows):,} rows, {len(todo)} of {len(batches)} batches to load", flush=True)

    t0 = time.time()
    loaded = len(rows) - sum(len(b) for _, b in todo)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(tp_client.upsert, namespace, b, kind): (i, len(b)) for i, b in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            i, size = futs[fut]
            fut.result()
            done.add(i)
            loaded += size
            if n % 10 == 0 or n == len(todo):
                json.dump(sorted(done), open(state_path, "w"))
                rate = loaded / max(1e-9, time.time() - t0)
                print(f"  {loaded:,}/{len(rows):,} loaded ({rate:,.0f} docs/s)", flush=True)
    json.dump(sorted(done), open(state_path, "w"))
    print(f"{namespace}: done in {time.time() - t0:,.0f}s", flush=True)
