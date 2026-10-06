"""Tests for skill registry: validation, save, sandbox run."""
import pytest

from app.skills import registry


GOOD = "def run(**kwargs):\n    return kwargs.get('x', 0) + 1\n"
BAD_BANNED = "import subprocess\ndef run(**kwargs): pass\n"
BAD_NO_RUN = "def hello(): pass\n"
BAD_SYNTAX = "def run(**kwargs)\n    pass\n"


def test_validate_ok():
    registry.validate(GOOD)


def test_validate_banned():
    with pytest.raises(registry.SkillError, match="banned"):
        registry.validate(BAD_BANNED)


def test_validate_no_run():
    with pytest.raises(registry.SkillError, match="missing run"):
        registry.validate(BAD_NO_RUN)


def test_validate_syntax():
    with pytest.raises(registry.SkillError, match="syntax"):
        registry.validate(BAD_SYNTAX)


def test_save_and_list(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.SKILLS_DIR", tmp_path)
    result = registry.save("add_one", GOOD, "adds 1")
    assert result["name"] == "add_one"
    assert "add_one" in registry.list_skills()


def test_save_bad_name(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.SKILLS_DIR", tmp_path)
    with pytest.raises(registry.SkillError, match="bad name"):
        registry.save("Bad Name!", GOOD)


def test_sandbox_run(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.SKILLS_DIR", tmp_path)
    monkeypatch.setattr("app.config.SKILL_EXEC", True)
    monkeypatch.setattr("app.config.SKILL_TIMEOUT", 5)
    registry.save("add_one", GOOD)
    assert registry.run("add_one", {"x": 4}) == 5


def test_sandbox_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.SKILLS_DIR", tmp_path)
    monkeypatch.setattr("app.config.SKILL_EXEC", True)
    monkeypatch.setattr("app.config.SKILL_TIMEOUT", 1)
    slow = "import time\ndef run(**kwargs):\n    time.sleep(10)\n    return 1\n"
    registry.save("slow_skill", slow)
    with pytest.raises(registry.SkillError, match="timeout"):
        registry.run("slow_skill", {})


def test_run_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.SKILLS_DIR", tmp_path)
    monkeypatch.setattr("app.config.SKILL_EXEC", False)
    registry.save("add_one", GOOD)
    with pytest.raises(registry.SkillError, match="exec disabled"):
        registry.run("add_one", {})
