import json
import threading
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config

DEFAULT_ID = "default"
DEFAULT_AGENT = {"id": DEFAULT_ID, "name": "Default agent", "model": "",
                 "system_prompt": "You are a helpful assistant."}

router = APIRouter(prefix="/api/agents")
_lock = threading.Lock()


class AgentIn(BaseModel):
    name: str
    model: str = ""
    system_prompt: str = ""


class AgentPatch(BaseModel):
    name: str | None = None
    model: str | None = None
    system_prompt: str | None = None


def _file():
    return config.MEMORY_DIR / "agents.json"


def _load() -> list[dict]:
    try:
        items = json.loads(_file().read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        items = []
    if not any(it.get("id") == DEFAULT_ID for it in items):
        items.insert(0, dict(DEFAULT_AGENT))
    return items


def _save(items: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")


@router.get("")
def list_agents():
    return _load()


@router.post("")
def create(a: AgentIn):
    if not a.name.strip():
        raise HTTPException(400, "name is required")
    with _lock:
        items = _load()
        item = {"id": uuid.uuid4().hex[:8], **a.model_dump()}
        items.append(item)
        _save(items)
    return item


@router.patch("/{agent_id}")
def update(agent_id: str, a: AgentPatch):
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == agent_id:
                it.update({k: v for k, v in a.model_dump().items() if v is not None})
                _save(items)
                return it
    raise HTTPException(404, "agent not found")


@router.delete("/{agent_id}")
def delete(agent_id: str):
    if agent_id == DEFAULT_ID:
        raise HTTPException(400, "the default agent cannot be deleted")
    with _lock:
        items = _load()
        kept = [it for it in items if it["id"] != agent_id]
        if len(kept) == len(items):
            raise HTTPException(404, "agent not found")
        _save(kept)
    return {"deleted": agent_id}
