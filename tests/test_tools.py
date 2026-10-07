import json

import pytest

from app import tools


@pytest.fixture
def d(tmp_path):
    return [str(tmp_path)]


def run(name, args, d):
    return tools.run(name, args, d)


def test_write_read_edit_roundtrip(tmp_path, d):
    assert run("write_file", {"path": "a/b.txt", "content": "hello\nworld\n"}, d)["ok"]
    assert run("read_file", {"path": "a/b.txt"}, d)["result"] == "hello\nworld\n"
    assert run("read_file", {"path": "a/b.txt", "head": 1}, d)["result"] == "hello"
    r = run("edit_file", {"path": "a/b.txt", "edits": [{"old": "world", "new": "there"}]}, d)
    assert r["ok"] and "+there" in r["result"]
    assert (tmp_path / "a" / "b.txt").read_text() == "hello\nthere\n"


def test_edit_requires_unique_match(tmp_path, d):
    (tmp_path / "x.txt").write_text("aa aa")
    r = run("edit_file", {"path": "x.txt", "edits": [{"old": "aa", "new": "b"}]}, d)
    assert not r["ok"] and "2 times" in r["result"]
    assert (tmp_path / "x.txt").read_text() == "aa aa"


def test_dry_run_changes_nothing(tmp_path, d):
    (tmp_path / "x.txt").write_text("one")
    run("edit_file", {"path": "x.txt", "edits": [{"old": "one", "new": "two"}], "dry_run": True}, d)
    assert (tmp_path / "x.txt").read_text() == "one"


def test_paths_outside_allowed_folders_are_refused(tmp_path, d):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    for p in (str(outside), "../outside.txt"):
        r = run("read_file", {"path": p}, d)
        assert not r["ok"] and "outside" in r["result"]
    assert not run("write_file", {"path": "../evil.txt", "content": "x"}, d)["ok"]


def test_symlink_escape_is_refused(tmp_path, d):
    target = tmp_path.parent / "elsewhere"
    target.mkdir(exist_ok=True)
    (target / "f.txt").write_text("x")
    (tmp_path / "link").symlink_to(target)
    assert not run("read_file", {"path": "link/f.txt"}, d)["ok"]


def test_list_find_search_tree(tmp_path, d):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('needle')\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.py").write_text("needle")
    assert "[DIR]  src/" in run("list_files", {}, d)["result"]
    assert "main.py" in run("find_files", {"pattern": "*.py"}, d)["result"]
    assert "skip.py" not in run("find_files", {"pattern": "*.py"}, d)["result"]
    s = run("search_in_files", {"query": "NEEDLE"}, d)["result"]
    assert "main.py:1" in s and "skip.py" not in s
    assert "src/" in run("folder_tree", {}, d)["result"]


def test_delete_moves_to_trash(tmp_path, d, monkeypatch):
    monkeypatch.setattr(tools.config, "ROOT", tmp_path / "root")
    (tmp_path / "x.txt").write_text("keep me")
    r = run("delete_path", {"path": "x.txt"}, d)
    assert r["ok"] and not (tmp_path / "x.txt").exists()
    assert list((tmp_path / "root" / ".trash").rglob("x.txt"))
    assert not run("delete_path", {"path": str(tmp_path)}, d)["ok"]


def test_move_and_copy_do_not_overwrite(tmp_path, d):
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "b.txt").write_text("2")
    assert not run("move_path", {"source": "a.txt", "destination": "b.txt"}, d)["ok"]
    assert run("copy_path", {"source": "a.txt", "destination": "c/a.txt"}, d)["ok"]
    assert run("move_path", {"source": "a.txt", "destination": "z.txt"}, d)["ok"]


def test_calculate_is_safe():
    assert run("calculate", {"expression": "(12.5*8)/4"}, [])["result"] == "25.0"
    assert not run("calculate", {"expression": "__import__('os').system('x')"}, [])["ok"]
    assert not run("calculate", {"expression": "9**9999"}, [])["ok"]
    assert not run("calculate", {"expression": "1/0"}, [])["ok"]


def test_run_command_in_allowed_folder(tmp_path, d):
    r = run("run_command", {"command": "echo hi"}, d)
    assert r["ok"] and "hi" in r["result"] and "exit code 0" in r["result"]
    assert not run("run_command", {"command": "echo hi", "folder": str(tmp_path.parent)}, d)["ok"]


def test_default_workspace_when_no_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.config, "ROOT", tmp_path)
    assert run("workspace_folders", {}, [])["result"] == str((tmp_path / "workspace").resolve())


def test_missing_argument_is_reported(d):
    r = run("read_file", {}, d)
    assert not r["ok"] and "path" in r["result"]


def test_unknown_and_client_tools_are_not_run(d):
    assert not run("nope", {}, d)["ok"]
    assert not run("ask_user", {"question": "x"}, d)["ok"]


def test_memory_tools(tmp_path, monkeypatch):
    from app.memory import store
    m = store.Memory(tmp_path / "m.db")
    monkeypatch.setattr(store, "memory", m)
    r = run("remember", {"fact": "The user prefers short answers"}, [])
    assert r["ok"] and "#" in r["result"]
    assert "short answers" in run("recall", {"query": "short"}, [])["result"]
    assert not run("remember", {"fact": "my password: hunter2"}, [])["ok"]
    fid = m.recent(1)[0]["id"]
    assert run("forget", {"id": fid}, [])["ok"] and not m.recent(5)


def test_url_guard_blocks_local_addresses():
    for u in ("http://127.0.0.1:11434/api/tags", "http://localhost/", "file:///etc/passwd"):
        r = run("open_url", {"url": u}, [])
        assert not r["ok"]


def test_html_to_text_and_search_parse():
    assert tools.html_to_text("<html><head><title>x</title></head><body><script>bad()</script><p>Hello</p><p>World</p></body></html>") == "Hello\n\nWorld"
    html = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example <b>A</b></a>'
            '<a class="result__snippet" href="x">About A</a>'
            '<a class="result__a" href="https://b.org/">B</a>')
    hits = tools.parse_search(html, 5)
    assert hits[0] == {"title": "Example A", "url": "https://example.com/a", "snippet": "About A"}
    assert hits[1]["url"] == "https://b.org/"


def test_listing_has_schema_for_every_tool():
    items = tools.listing()
    assert len(items) == len(tools.REGISTRY) >= 25
    for it in items:
        assert it["schema"]["function"]["name"] == it["name"] and it["description"]
        json.dumps(it["schema"])
    assert {"use_tools", "ask_user", "update_plan"} <= {i["name"] for i in items if i["client"]}
    assert {i["kind"] for i in items} <= {"read", "net", "memory", "write", "exec", "ui"}
