"""Persistent local memory: SQLite + FTS5 in .memory/."""
import os
import re
import sqlite3
import threading
import time

from app import config

_SENT = re.compile(r"(?<=[.!])\s+")
_MIN_FACT = 30  # chars; shorter sentences rarely carry standalone facts

_AR_DIAC = re.compile("[\u064b-\u065f\u0670\u0640]")
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
_WORD = re.compile(r"\w+", re.UNICODE)
_PREFIXES = ("وال", "فال", "بال", "لل", "كال", "ال", "و", "ف", "ب", "ل", "ك")


def norm(text: str) -> str:
    """Lowercase, strip Arabic diacritics, merge alef/ta-marbuta/ya variants."""
    return _AR_DIAC.sub("", text or "").translate(_AR_MAP).lower()


def _stem(w: str) -> str:
    for p in _PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 3:
            return w[len(p):]
    return w


def words(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(norm(text)) if len(w) > 1]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, kind TEXT, content TEXT, tags TEXT, ts REAL, norm TEXT);
CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, model TEXT, prompt TEXT, response TEXT, ts REAL);
"""

_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(norm, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, norm) VALUES (new.id, new.norm); END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, norm) VALUES ('delete', old.id, old.norm); END;
"""


class Memory:
    def __init__(self, path=None, mirror=None):
        path = path or config.MEMORY_DIR / "memory.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.mirror = mirror  # optional semantic backend (see app/memory/mnemosyne.py)
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self):
        cols = [r[1] for r in self._db.execute("PRAGMA table_info(facts)")]
        if "norm" not in cols:  # old layout: FTS over (content, tags)
            self._db.executescript("DROP TRIGGER IF EXISTS facts_ai; DROP TRIGGER IF EXISTS facts_ad;"
                                   "DROP TABLE IF EXISTS facts_fts; ALTER TABLE facts ADD COLUMN norm TEXT;")
            for r in self._db.execute("SELECT id, content, tags FROM facts").fetchall():
                self._db.execute("UPDATE facts SET norm=? WHERE id=?",
                                 (" ".join(words(f"{r['content']} {r['tags'] or ''}")), r["id"]))
            self._db.commit()
        self._db.executescript(_FTS)
        if "norm" not in cols:
            self._db.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
            self._db.commit()

    def _x(self, sql, args=()):
        with self._lock, self._db:
            return self._db.execute(sql, args).fetchall()

    def add(self, content: str, kind="fact", tags="") -> int:
        with self._lock, self._db:
            fid = self._db.execute("INSERT INTO facts(kind,content,tags,ts,norm) VALUES(?,?,?,?,?)",
                                   (kind, content, tags, time.time(), " ".join(words(f"{content} {tags}")))).lastrowid
        if self.mirror:
            self.mirror.remember(content)
        return fid

    def search(self, q: str, k=5) -> list[dict]:
        ws = list(dict.fromkeys(words(q)))
        if not ws:
            return []
        terms = " OR ".join(f'"{w}"*' for w in ws)
        rows = [dict(r) for r in self._x(
            "SELECT f.* FROM facts_fts JOIN facts f ON f.id=facts_fts.rowid "
            "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?", (terms, k))]
        if self.mirror and len(rows) < k:
            have = {r["id"] for r in rows}
            for text in self.mirror.recall(q, k):
                for r in self._x("SELECT * FROM facts WHERE content=? LIMIT 1", (text,)):
                    if r["id"] not in have:
                        have.add(r["id"])
                        rows.append(dict(r))
        return rows[:k]

    def recent(self, k=20) -> list[dict]:
        return [dict(r) for r in self._x("SELECT * FROM facts ORDER BY id DESC LIMIT ?", (k,))]

    def relevant(self, q: str, k=5, recent=5) -> list[dict]:
        """Facts matching the query plus the newest ones, deduplicated."""
        out = self.search(q, k)
        seen = {f["id"] for f in out}
        out += [f for f in self.recent(recent) if f["id"] not in seen]
        return out

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


def _make() -> "Memory":
    if os.environ.get("HERAMA_MEMORY_BACKEND", "sqlite").lower() == "mnemosyne":
        from app.memory.mnemosyne import load
        return Memory(mirror=load())
    return Memory()


memory = _make()
