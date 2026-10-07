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
