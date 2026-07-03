"""SQLite data store with JSON exports.

Layout under the data directory:
    edgegroup.db   — SQLite database (canonical store)
    json/          — one JSON file per section, exported after each run
    images/        — downloaded images, per section/slug

Records are upserted by URL; first_seen/last_updated timestamps and a
content hash make change tracking cheap between monthly runs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    url TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT,
    category TEXT,
    entity TEXT,
    description TEXT,
    specifications TEXT,   -- JSON object
    images TEXT,           -- JSON array of {url, alt, source, local_path}
    body_text TEXT,
    meta TEXT,             -- JSON object
    content_hash TEXT,
    first_seen TEXT,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS entities (
    url TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT,
    cluster TEXT,
    description TEXT,
    website TEXT,
    product_urls TEXT,     -- JSON array
    images TEXT,
    body_text TEXT,
    meta TEXT,
    content_hash TEXT,
    first_seen TEXT,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS news (
    url TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    title TEXT,
    published_date TEXT,
    description TEXT,
    is_partnership INTEGER DEFAULT 0,
    images TEXT,
    body_text TEXT,
    meta TEXT,
    content_hash TEXT,
    first_seen TEXT,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS partnerships (
    source_url TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    date TEXT,
    source TEXT,           -- 'news' or 'page'
    content_hash TEXT,
    first_seen TEXT,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    section TEXT,          -- 'group', 'cluster', 'partnerships', ...
    name TEXT,
    description TEXT,
    images TEXT,
    body_text TEXT,
    meta TEXT,
    content_hash TEXT,
    first_seen TEXT,
    last_updated TEXT
);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started TEXT,
    finished TEXT,
    status TEXT,
    sections TEXT,
    pages_scraped INTEGER DEFAULT 0,
    errors TEXT
);
"""

_JSON_FIELDS = {"specifications", "images", "meta", "product_urls", "jsonld"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DataStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "edgegroup.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- runs ---------------------------------------------------------

    def start_run(self, sections: list[str]) -> int:
        cur = self.conn.execute(
            "INSERT INTO scrape_runs (started, status, sections) VALUES (?, 'running', ?)",
            (_now(), ",".join(sections)),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, pages: int, errors: list[str]) -> None:
        self.conn.execute(
            "UPDATE scrape_runs SET finished=?, status=?, pages_scraped=?, errors=? WHERE id=?",
            (_now(), status, pages, json.dumps(errors[:50]), run_id),
        )
        self.conn.commit()

    # -- upserts ------------------------------------------------------

    def upsert(self, table: str, record: dict, key: str = "url") -> None:
        columns = self._columns(table)
        row = {}
        for col in columns:
            if col in ("first_seen", "last_updated", "content_hash"):
                continue
            value = record.get(col)
            if col in _JSON_FIELDS or isinstance(value, (dict, list)):
                value = json.dumps(value or ({} if col in ("specifications", "meta") else []),
                                   ensure_ascii=False)
            if isinstance(value, bool):
                value = int(value)
            row[col] = value

        content_hash = hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        existing = self.conn.execute(
            f"SELECT content_hash, first_seen FROM {table} WHERE {key}=?", (row[key],)
        ).fetchone()

        now = _now()
        if existing and existing["content_hash"] == content_hash:
            return
        row["content_hash"] = content_hash
        row["first_seen"] = existing["first_seen"] if existing else now
        row["last_updated"] = now

        cols = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        self.conn.commit()

    def _columns(self, table: str) -> list[str]:
        return [r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")]

    # -- exports ------------------------------------------------------

    def export_json(self) -> None:
        out = self.data_dir / "json"
        out.mkdir(exist_ok=True)
        for table in ("products", "entities", "news", "partnerships", "pages"):
            rows = []
            for row in self.conn.execute(f"SELECT * FROM {table} ORDER BY 1"):
                item = dict(row)
                item.pop("content_hash", None)
                for field in _JSON_FIELDS:
                    if isinstance(item.get(field), str):
                        try:
                            item[field] = json.loads(item[field])
                        except json.JSONDecodeError:
                            pass
                rows.append(item)
            (out / f"{table}.json").write_text(
                json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    def counts(self) -> dict[str, int]:
        return {
            table: self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("products", "entities", "news", "partnerships", "pages")
        }
