import json
import threading
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config

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
        return json.loads(_file().read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return []


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
    with _lock:
        items = _load()
        kept = [it for it in items if it["id"] != agent_id]
        if len(kept) == len(items):
            raise HTTPException(404, "agent not found")
        _save(kept)
    return {"deleted": agent_id}
