import sys
import types

if "llama_cpp" not in sys.modules:
    lm = types.ModuleType("llama_cpp")
    lm.Llama = type("Llama", (), {"__init__": lambda s, **k: None})
    sys.modules["llama_cpp"] = lm

import app.config as cfg
from fastapi.testclient import TestClient
from app import tools
from app.main import app

client = TestClient(app)


def test_group_crud_and_scoped_team(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path)
    a = client.post("/api/agents", json={"name": "Lead", "model": "m"}).json()["id"]
    b = client.post("/api/agents", json={"name": "Writer", "model": "m"}).json()["id"]
    c = client.post("/api/agents", json={"name": "Outsider", "model": "m"}).json()["id"]
    assert client.post("/api/groups", json={"name": "t", "lead": "nope"}).status_code == 400
    g = client.post("/api/groups", json={"name": "Team", "lead": a, "members": [b, b, a, "ghost"]}).json()
    assert g["members"] == [b]
    # inside the group the lead sees only its member; outside it sees everyone
    inside = tools.run("list_agents", {}, agent=a, group=g["id"])["result"]
    assert "Writer" in inside and "Outsider" not in inside
    assert "Outsider" in tools.run("list_agents", {}, agent=a)["result"]
    assert not tools.run("ask_agent", {"agent": "Outsider", "task": "x"}, agent=a, model="m", group=g["id"])["ok"]
    assert client.patch(f"/api/groups/{g['id']}", json={"members": [b, c]}).json()["members"] == [b, c]
    assert client.delete(f"/api/groups/{g['id']}").status_code == 200
    assert client.delete(f"/api/groups/{g['id']}").status_code == 404


def test_agent_prompt_files_and_model_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path)
    a = client.post("/api/agents", json={"name": "Writer", "model": "gone", "soul": "Calm.", "instructions": "Write short.", "system_prompt": "Extra."}).json()
    assert a["prompt"] == "# SOUL\nCalm.\n\n# AGENT\nWrite short.\n\nExtra."
    b = client.patch(f"/api/agents/{a['id']}", json={"soul": ""}).json()
    assert b["prompt"].startswith("# AGENT") and b["instructions"] == "Write short."
    old = client.get("/api/agents").json()[0]  # the default agent has the new fields too
    assert old["soul"] == "" and old["prompt"] == "You are a helpful assistant."
    from app import tools
    ctx = tools.make_ctx([], [], False, "default", "fallback-model", "")
    seen = {}

    class Eng:
        def path(self, n):
            raise FileNotFoundError(n)

        def chat(self, model, msgs, opts, stream):
            seen["model"], seen["system"] = model, msgs[0]["content"]
            yield "ok"
            yield {}

    import app.engine as eng
    monkeypatch.setattr(eng, "engine", Eng())
    out = tools._ask_agent({"agent": a["id"], "task": "hi"}, ctx)
    assert seen["model"] == "fallback-model" and "# AGENT" in seen["system"] and "answered" in out
