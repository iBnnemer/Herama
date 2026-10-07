"""Tests for memory store: add, search, extract_facts."""
import pytest

from app.memory.store import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(tmp_path / "test.db")


def test_add_and_recent(mem):
    mem.add("Paris is the capital of France.")
    rows = mem.recent(5)
    assert rows[0]["content"] == "Paris is the capital of France."


def test_search(mem):
    mem.add("The Eiffel Tower is in Paris.")
    mem.add("Mount Fuji is in Japan.")
    results = mem.search("Paris")
    assert any("Paris" in r["content"] for r in results)


def test_delete(mem):
    fid = mem.add("temporary fact")
    mem.delete(fid)
    assert not any(r["id"] == fid for r in mem.recent())


def test_extract_facts(mem):
    text = ("The sky is blue on clear days. It can also appear red at sunset. "
            "Short.")
    ids = mem.extract_facts(text)
    assert len(ids) == 2  # "Short." is below _MIN_FACT


def test_log_turn_auto_extract(mem):
    mem.log_turn("m", "prompt",
                 "The sun is a star at the center of our solar system. "
                 "It provides light and heat to all the planets.",
                 auto_extract=True)
    rows = mem.recent()
    assert any(r["kind"] == "auto" for r in rows)


def test_arabic_search_and_relevant(tmp_path):
    from app.memory.store import Memory
    m = Memory(tmp_path / "ar.db")
    m.add("المستخدم يحب القهوة في الصباح")
    m.add("fact about something unrelated here")
    assert m.search("القهوه")  # ta-marbuta / ha merge
    assert m.search("والقهوة")  # prefix stripped
    ids = [f["id"] for f in m.relevant("قهوة", k=1, recent=5)]
    assert len(ids) == len(set(ids)) == 2


def test_migration_from_old_schema(tmp_path):
    import sqlite3
    from app.memory.store import Memory
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE facts(id INTEGER PRIMARY KEY, kind TEXT, content TEXT, tags TEXT, ts REAL);"
                    "INSERT INTO facts(content,tags) VALUES('Paris is the capital','x');")
    c.commit(); c.close()
    assert Memory(p).search("Paris")


def test_mirror_union(tmp_path):
    from app.memory.store import Memory

    class Fake:
        def __init__(self): self.saved = []
        def remember(self, t): self.saved.append(t)
        def recall(self, q, k): return ["semantic only match text here"]
    f = Fake()
    m = Memory(tmp_path / "m.db", mirror=f)
    m.add("semantic only match text here")
    assert f.saved and m.search("zzzz")[0]["content"].startswith("semantic")
