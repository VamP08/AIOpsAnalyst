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
CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  tier TEXT NOT NULL
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

    @staticmethod
    def _to_event(row) -> Event:
        fields = dict(zip(_COLS, row))
        fields["attributes"] = json.loads(fields["attributes"] or "{}")
        return Event(**fields)

    def get_event(self, event_id: str) -> Event | None:
        row = self.db.execute(
            f"SELECT {','.join(_COLS)} FROM events WHERE id = ?",
            (event_id,)).fetchone()
        return self._to_event(row) if row else None

    def all_events(self) -> list[Event]:
        rows = self.db.execute(
            f"SELECT {','.join(_COLS)} FROM events ORDER BY rowid").fetchall()
        return [self._to_event(r) for r in rows]

    def unclustered_events(self) -> list[Event]:
        rows = self.db.execute(
            f"SELECT {','.join(_COLS)} FROM events "
            "WHERE clusterid IS NULL ORDER BY rowid").fetchall()
        return [self._to_event(r) for r in rows]

    def assign_clusters(self, assignment: dict[str, str],
                        clusters: dict[str, tuple[str, str]]) -> None:
        self.db.executemany(
            "UPDATE events SET clusterid = ? WHERE id = ?",
            [(cid, eid) for eid, cid in assignment.items()])
        self.db.executemany(
            "INSERT INTO clusters (id, label, tier) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET label = excluded.label",
            [(cid, label, tier) for cid, (label, tier) in clusters.items()])
        self.db.commit()

    def list_clusters(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.id, c.label, c.tier, COUNT(e.id) "
            "FROM clusters c LEFT JOIN events e ON e.clusterid = c.id "
            "GROUP BY c.id ORDER BY COUNT(e.id) DESC").fetchall()
        return [{"id": r[0], "label": r[1], "tier": r[2], "size": r[3]}
                for r in rows]

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
