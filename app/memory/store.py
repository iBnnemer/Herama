"""Persistent local memory: SQLite + FTS5 in .memory/."""
import re
import sqlite3
import threading
import time

from app import config

_SENT = re.compile(r"(?<=[.!])\s+")
_MIN_FACT = 30  # chars; shorter sentences rarely carry standalone facts

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, kind TEXT, content TEXT, tags TEXT, ts REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(content, tags, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags); END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, content, tags) VALUES ('delete', old.id, old.content, old.tags); END;
CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, model TEXT, prompt TEXT, response TEXT, ts REAL);
"""


class Memory:
    def __init__(self, path=None):
        path = path or config.MEMORY_DIR / "memory.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def _x(self, sql, args=()):
        with self._lock, self._db:
            return self._db.execute(sql, args).fetchall()

    def add(self, content: str, kind="fact", tags="") -> int:
        with self._lock, self._db:
            return self._db.execute("INSERT INTO facts(kind,content,tags,ts) VALUES(?,?,?,?)",
                                    (kind, content, tags, time.time())).lastrowid

    def search(self, q: str, k=5) -> list[dict]:
        terms = " OR ".join(f'"{w}"' for w in q.replace('"', " ").split() if w)
        if not terms:
            return []
        rows = self._x("SELECT f.* FROM facts_fts JOIN facts f ON f.id=facts_fts.rowid "
                       "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?", (terms, k))
        return [dict(r) for r in rows]

    def recent(self, k=20) -> list[dict]:
        return [dict(r) for r in self._x("SELECT * FROM facts ORDER BY id DESC LIMIT ?", (k,))]

    def delete(self, fid: int):
        self._x("DELETE FROM facts WHERE id=?", (fid,))

    def log_turn(self, model, prompt, response, auto_extract=False):
        self._x("INSERT INTO turns(model,prompt,response,ts) VALUES(?,?,?,?)",
                (model, prompt, response, time.time()))
        if auto_extract and response:
            self.extract_facts(response, tags="auto")

    def extract_facts(self, text: str, tags="auto") -> list[int]:
        """Split text into sentences and store declarative ones as facts."""
        ids = []
        for sent in _SENT.split(text.strip()):
            sent = sent.strip()
            if (len(sent) >= _MIN_FACT
                    and not sent.endswith("?")
                    and not sent.startswith("#")):
                ids.append(self.add(sent, kind="auto", tags=tags))
        return ids


memory = Memory()
