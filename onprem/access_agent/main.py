from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path


DB_PATH = Path(os.getenv("ACCESS_AGENT_DB", "/tmp/access-agent.sqlite3"))
ALLOWLIST_URL = os.getenv("ACCESS_ALLOWLIST_URL", "http://localhost:8000/api/access/allowlist/")
ACCESS_AGENT_API_KEY = os.getenv("ACCESS_AGENT_API_KEY", "")
POLL_SECONDS = int(os.getenv("ACCESS_AGENT_POLL_SECONDS", "300"))


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS allowlist_snapshots (
            etag TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            signature TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            stored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def latest_etag(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT etag FROM allowlist_snapshots ORDER BY stored_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def fetch_snapshot(etag: str | None) -> dict | None:
    url = ALLOWLIST_URL
    if etag:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}v={etag}"
    headers = {"Accept": "application/json"}
    if ACCESS_AGENT_API_KEY:
        headers["X-Access-Agent-Key"] = ACCESS_AGENT_API_KEY
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status == 304:
                return None
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None
        raise


def store_snapshot(connection: sqlite3.Connection, snapshot: dict) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO allowlist_snapshots (etag, generated_at, signature, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            snapshot["etag"],
            snapshot["generated_at"],
            snapshot["signature"],
            json.dumps(snapshot["payload"], sort_keys=True),
        ),
    )
    connection.commit()


def poll_once(connection: sqlite3.Connection) -> bool:
    etag = latest_etag(connection)
    snapshot = fetch_snapshot(etag)
    if not snapshot:
        return False
    store_snapshot(connection, snapshot)
    return True


def main() -> None:
    connection = init_db()
    while True:
        try:
            updated = poll_once(connection)
            print("allowlist updated" if updated else "allowlist unchanged", flush=True)
        except Exception as exc:  # pragma: no cover
            print(f"access-agent poll failed: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
