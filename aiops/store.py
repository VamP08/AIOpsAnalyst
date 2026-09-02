"""SQLite persistence. Local-first: one file, no server.

Event ids are the idempotency boundary — sources make ids deterministic,
INSERT OR IGNORE makes re-ingestion a no-op, and insert_events reports how many
rows were actually new so callers can see dedup working. Cursors give stateless
runs (a cron job, a re-run CLI) a saved position per source.
"""
import json
import sqlite3

from aiops.envelope import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  type TEXT NOT NULL,
  time TEXT,
  subject TEXT,
  datacontenttype TEXT,
  severitytext TEXT,
  severitynumber INTEGER,
  fingerprint TEXT,
  clusterid TEXT,
  title TEXT NOT NULL,
  body TEXT,
  attributes TEXT,
  url TEXT,
  raw TEXT
);
CREATE TABLE IF NOT EXISTS cursors (
  source TEXT PRIMARY KEY,
  cursor TEXT NOT NULL
);
"""

_COLS = ("id", "source", "type", "time", "subject", "datacontenttype",
         "severitytext", "severitynumber", "fingerprint", "clusterid",
         "title", "body", "attributes", "url", "raw")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)

    def insert_events(self, events) -> int:
        rows = [tuple(json.dumps(e.attributes) if col == "attributes"
                      else getattr(e, col) for col in _COLS)
                for e in events]
        before = self.db.total_changes
        self.db.executemany(
            f"INSERT OR IGNORE INTO events ({','.join(_COLS)}) "
            f"VALUES ({','.join('?' * len(_COLS))})", rows)
        self.db.commit()
        return self.db.total_changes - before

    def count_events(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def get_event(self, event_id: str) -> Event | None:
        row = self.db.execute(
            f"SELECT {','.join(_COLS)} FROM events WHERE id = ?",
            (event_id,)).fetchone()
        if row is None:
            return None
        fields = dict(zip(_COLS, row))
        fields["attributes"] = json.loads(fields["attributes"] or "{}")
        return Event(**fields)

    def get_cursor(self, source: str) -> str | None:
        row = self.db.execute("SELECT cursor FROM cursors WHERE source = ?",
                              (source,)).fetchone()
        return row[0] if row else None

    def set_cursor(self, source: str, cursor: str) -> None:
        self.db.execute(
            "INSERT INTO cursors (source, cursor) VALUES (?, ?) "
            "ON CONFLICT(source) DO UPDATE SET cursor = excluded.cursor",
            (source, cursor))
        self.db.commit()
