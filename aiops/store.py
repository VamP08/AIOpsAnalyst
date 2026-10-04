"""SQLite persistence. Local-first: one file, no server.

Event ids are the idempotency boundary — sources make ids deterministic,
INSERT OR IGNORE makes re-ingestion a no-op, and insert_events reports how many
rows were actually new so callers can see dedup working. Cursors give stateless
runs (a cron job, a re-run CLI) a saved position per source.
"""
import json
import re
import sqlite3
import threading

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
CREATE INDEX IF NOT EXISTS events_clusterid ON events(clusterid);
CREATE TABLE IF NOT EXISTS cursors (
  source TEXT PRIMARY KEY,
  cursor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  tier TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routed (
  clusterid TEXT NOT NULL,
  sink TEXT NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (clusterid, sink)
);
CREATE TABLE IF NOT EXISTS verdicts (
  clusterid TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,
  summary TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence TEXT NOT NULL,
  tier TEXT NOT NULL,
  model TEXT NOT NULL,
  promptversion TEXT NOT NULL,
  created TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# FTS5 treats these as operators; a question that contains one is asking in
# English, not in query syntax.
_FTS_KEYWORDS = {"and", "or", "not", "near"}

_SEARCH_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS cluster_search
USING fts5(clusterid UNINDEXED, label, summary, tokenize='porter unicode61');
"""

_COLS = ("id", "source", "type", "time", "subject", "datacontenttype",
         "severitytext", "severitynumber", "fingerprint", "clusterid",
         "title", "body", "attributes", "url", "raw")


class Store:
    """One connection per thread.

    The API serves reads from a threadpool, and the dashboard asks for two
    endpoints at once; a single shared sqlite connection used from two threads
    at the same moment raises "bad parameter or other API misuse" rather than
    blocking, so each thread gets its own. WAL lets those readers run while the
    pipeline writes from another process, which is exactly what happens when
    someone watches the demo during an ingest.
    """

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        self.db.executescript(_SCHEMA)

    @property
    def db(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")
            self._local.connection = connection
        return connection

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

    def prune_clusters(self, keep) -> int:
        """Drop every cluster not in `keep`, with its verdict. For a whole-
        corpus recluster only: a cluster it did not produce has no events left,
        and its verdict would otherwise keep counting. Routed rows stay - they
        record side effects that really happened."""
        self.db.execute("CREATE TEMP TABLE IF NOT EXISTS keep_ids (id TEXT)")
        self.db.execute("DELETE FROM keep_ids")
        self.db.executemany("INSERT INTO keep_ids VALUES (?)",
                            [(cid,) for cid in keep])
        dropped = self.db.execute(
            "DELETE FROM clusters WHERE id NOT IN (SELECT id FROM keep_ids)"
        ).rowcount
        self.db.execute("DELETE FROM verdicts WHERE clusterid NOT IN "
                        "(SELECT id FROM keep_ids)")
        self.db.commit()
        return dropped

    def list_clusters(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.id, c.label, c.tier, COUNT(e.id) "
            "FROM clusters c LEFT JOIN events e ON e.clusterid = c.id "
            "GROUP BY c.id ORDER BY COUNT(e.id) DESC").fetchall()
        return [{"id": r[0], "label": r[1], "tier": r[2], "size": r[3]}
                for r in rows]

    def clusters_without_verdict(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.id, c.label, c.tier FROM clusters c "
            "LEFT JOIN verdicts v ON v.clusterid = c.id "
            "WHERE v.clusterid IS NULL ORDER BY c.id").fetchall()
        return [{"id": r[0], "label": r[1], "tier": r[2]} for r in rows]

    def events_in_cluster(self, cluster_id: str, limit: int = 5) -> list[Event]:
        rows = self.db.execute(
            f"SELECT {','.join(_COLS)} FROM events WHERE clusterid = ? "
            "ORDER BY rowid LIMIT ?", (cluster_id, limit)).fetchall()
        return [self._to_event(r) for r in rows]

    def upsert_verdict(self, cluster_id: str, verdict: dict) -> None:
        self.db.execute(
            "INSERT INTO verdicts (clusterid, category, severity, summary, "
            "confidence, evidence, tier, model, promptversion) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(clusterid) DO UPDATE SET category = excluded.category, "
            "severity = excluded.severity, summary = excluded.summary, "
            "confidence = excluded.confidence, evidence = excluded.evidence, "
            "tier = excluded.tier, model = excluded.model, "
            "promptversion = excluded.promptversion",
            (cluster_id, verdict["category"], verdict["severity"],
             verdict["summary"], verdict["confidence"],
             json.dumps(verdict["evidence"]), verdict["tier"],
             verdict["model"], verdict["promptversion"]))
        self.db.commit()

    def get_verdict(self, cluster_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT category, severity, summary, confidence, evidence, tier, "
            "model, promptversion, created FROM verdicts WHERE clusterid = ?",
            (cluster_id,)).fetchone()
        if row is None:
            return None
        keys = ("category", "severity", "summary", "confidence", "evidence",
                "tier", "model", "promptversion", "created")
        verdict = dict(zip(keys, row))
        verdict["evidence"] = json.loads(verdict["evidence"])
        return verdict

    def record_routed(self, cluster_id: str, sink: str, ref: str | None) -> None:
        """Written only after a sink reports success: an unrecorded emit is
        retried next run, a recorded one is never sent twice."""
        self.db.execute(
            "INSERT OR REPLACE INTO routed (clusterid, sink, ref) "
            "VALUES (?, ?, ?)", (cluster_id, sink, ref or ""))
        self.db.commit()

    def routed(self, cluster_id: str) -> dict[str, str]:
        return {sink: ref for sink, ref in self.db.execute(
            "SELECT sink, ref FROM routed WHERE clusterid = ?",
            (cluster_id,)).fetchall()}

    def search_clusters(self, question: str, limit: int = 8) -> list[dict]:
        """Full-text search over cluster templates and their summaries.

        The index is built on demand rather than kept in triggers: the corpus
        changes in batches between runs, not per keystroke, and a rebuild of a
        few hundred rows costs less than the machinery to keep it live.

        A question is not an FTS expression - quotes, question marks and a bare
        OR are all syntax to SQLite and all noise to a reader - so the query is
        reduced to its words and joined with OR.
        """
        self.db.executescript(_SEARCH_SCHEMA)
        self.db.execute("DELETE FROM cluster_search")
        self.db.execute(
            "INSERT INTO cluster_search (clusterid, label, summary) "
            "SELECT c.id, c.label, COALESCE(v.summary, '') FROM clusters c "
            "LEFT JOIN verdicts v ON v.clusterid = c.id")
        self.db.commit()

        words = [w for w in re.findall(r"[A-Za-z0-9_]+", question.lower())
                 if w not in _FTS_KEYWORDS and len(w) > 1]
        if not words:
            return []
        rows = self.db.execute(
            "SELECT s.clusterid, c.label, c.tier, bm25(cluster_search) AS rank "
            "FROM cluster_search s JOIN clusters c ON c.id = s.clusterid "
            "WHERE cluster_search MATCH ? ORDER BY rank LIMIT ?",
            (" OR ".join(words), limit)).fetchall()
        return [{"id": r[0], "label": r[1], "tier": r[2], "rank": r[3]}
                for r in rows]

    def timespan(self, cluster_id: str) -> dict:
        row = self.db.execute(
            "SELECT MIN(time), MAX(time), COUNT(*) FROM events "
            "WHERE clusterid = ?", (cluster_id,)).fetchone()
        return {"first": row[0], "last": row[1], "events": row[2]}

    def routed_map(self) -> dict[str, dict[str, str]]:
        """Every cluster's sink references in one query, for list views that
        would otherwise ask per row."""
        out: dict[str, dict[str, str]] = {}
        for cluster_id, sink, ref in self.db.execute(
                "SELECT clusterid, sink, ref FROM routed"):
            out.setdefault(cluster_id, {})[sink] = ref
        return out

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
