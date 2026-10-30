"""Resumable bounded acquisition; raw pages are committed individually to SQLite."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import zlib

from .source import AccessBlocked, Client


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def open_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("CREATE TABLE IF NOT EXISTS pages (number INTEGER PRIMARY KEY, "
                     "fetched_at TEXT NOT NULL, sha256 TEXT NOT NULL, payload BLOB NOT NULL)")
    database.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    database.commit()
    return database


def save_page(database, number, data, *, commit=True):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    database.execute("INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?)",
                     (number, utcnow(), hashlib.sha256(raw).hexdigest(), zlib.compress(raw)))
    if commit:
        database.commit()


def collect(database_path, workers=3, interval=1.0, max_pages=None, batch_size=20):
    database = open_database(database_path)
    client = Client(interval)
    started = time.monotonic()
    first = client.page(1)
    previous = database.execute("SELECT payload FROM pages WHERE number=1").fetchone()
    if previous and json.loads(zlib.decompress(previous[0])) != first:
        database.close()
        raise RuntimeError("Page 1 changed since this collection began. Start a new database; "
                           "existing pages were preserved. Do not mix generations.")
    save_page(database, 1, first)
    total_pages = first["totalPages"]
    if not isinstance(total_pages, int) or total_pages < 1:
        raise ValueError("Invalid totalPages")
    database.execute("INSERT OR IGNORE INTO metadata VALUES ('startedAt', ?)", (utcnow(),))
    database.execute("INSERT OR REPLACE INTO metadata VALUES ('sourceMetadata', ?)",
                     (json.dumps({k: v for k, v in first.items() if k != "rankingNodes"}),))
    database.execute("INSERT OR REPLACE INTO metadata VALUES ('status', 'collecting')")
    database.execute("DELETE FROM metadata WHERE key='lastError'")
    database.commit()
    existing = {row[0] for row in database.execute("SELECT number FROM pages")}
    missing = [n for n in range(1, total_pages + 1) if n not in existing]
    if max_pages is not None:
        missing = missing[:max(0, max_pages - len(existing))]
    batches = iter([missing[i:i + batch_size] for i in range(0, len(missing), batch_size)])
    completed = len(existing)
    print(json.dumps({"event": "start", "savedPages": completed,
                      "totalPages": total_pages, "reportedUsers": first["totalUsers"],
                      "workers": workers, "requestIntervalSeconds": interval}), flush=True)
    error = None
    fetch_seconds = write_seconds = 0.0
    fetched_batches = 0

    def fetch_batch(batch):
        before = time.monotonic()
        result = client.pages(batch)
        return result, time.monotonic() - before

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def submit_next():
            batch = next(batches, None)
            if batch is not None:
                pending[pool.submit(fetch_batch, batch)] = batch

        for _ in range(workers):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try:
                    results, duration = future.result()
                    fetch_seconds += duration
                    fetched_batches += 1
                    before = time.monotonic()
                    with database:
                        for number, data in results.items():
                            if data["totalPages"] != total_pages:
                                raise RuntimeError("Source totalPages changed during collection")
                            if not data["rankingNodes"]:
                                raise RuntimeError(f"Empty advertised page {number}")
                            save_page(database, number, data, commit=False)
                    completed += len(results)
                    write_seconds += time.monotonic() - before
                    if completed % 100 < batch_size or not pending:
                        print(json.dumps({"event": "progress", "savedPages": completed,
                                          "totalPages": total_pages,
                                          "meanBatchFetchSeconds": round(fetch_seconds / fetched_batches, 3),
                                          "totalWriteSeconds": round(write_seconds, 3),
                                          "elapsedSeconds": round(time.monotonic() - started, 1)}),
                              flush=True)
                except Exception as caught:
                    error = caught
                    break
                submit_next()
            if error:
                for future in pending:
                    future.cancel()
                break
    status = "blocked" if isinstance(error, AccessBlocked) else "failed" if error else (
        "collected" if completed == total_pages else "partial")
    database.execute("INSERT OR REPLACE INTO metadata VALUES ('status', ?)", (status,))
    database.execute("INSERT OR REPLACE INTO metadata VALUES ('lastRunAt', ?)", (utcnow(),))
    if error:
        database.execute("INSERT OR REPLACE INTO metadata VALUES ('lastError', ?)", (str(error),))
    database.commit()
    database.close()
    print(json.dumps({"event": status, "savedPages": completed, "totalPages": total_pages,
                      "error": str(error) if error else None}), flush=True)
    if error:
        raise error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/raw/rankings.sqlite3")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--batch-size", type=int, choices=range(1, 21), default=20)
    args = parser.parse_args()
    if args.interval < 0.25:
        parser.error("--interval must be at least 0.25 seconds")
    try:
        collect(args.database, args.workers, args.interval, args.max_pages, args.batch_size)
    except (Exception, KeyboardInterrupt) as error:
        database = open_database(args.database)
        status = ("interrupted" if isinstance(error, KeyboardInterrupt) else
                  "blocked" if isinstance(error, AccessBlocked) else "failed")
        database.execute("INSERT OR REPLACE INTO metadata VALUES ('status', ?)", (status,))
        database.execute("INSERT OR REPLACE INTO metadata VALUES ('lastError', ?)", (str(error),))
        database.commit()
        database.close()
        print(json.dumps({"event": status, "error": str(error)}), flush=True)
        raise SystemExit(130 if isinstance(error, KeyboardInterrupt) else 1)


if __name__ == "__main__":
    main()
