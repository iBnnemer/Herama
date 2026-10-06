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
