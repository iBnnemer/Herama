"""Agent groups: a lead agent plus members that work together in one shared chat."""
import json
import threading
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config

router = APIRouter(prefix="/api/groups")
_lock = threading.Lock()


class GroupIn(BaseModel):
    name: str
    lead: str
    members: list[str] = []


class GroupPatch(BaseModel):
    name: str | None = None
    lead: str | None = None
    members: list[str] | None = None


def _file():
    return config.MEMORY_DIR / "groups.json"


def _load() -> list[dict]:
    try:
        return json.loads(_file().read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")


def get(group_id: str) -> dict | None:
    return next((g for g in _load() if g["id"] == group_id), None)


def _clean(name: str, lead: str, members: list[str]) -> dict:
    from app.api import agents
    known = {a["id"] for a in agents._load()}
    if not name.strip():
        raise HTTPException(400, "name is required")
    if lead not in known:
        raise HTTPException(400, "the lead must be an existing agent")
    ids = [m for m in dict.fromkeys(members) if m in known and m != lead]
    return {"name": name.strip(), "lead": lead, "members": ids}


@router.get("")
def list_groups():
    return _load()


@router.post("")
def create(g: GroupIn):
    item = {"id": uuid.uuid4().hex[:8], **_clean(g.name, g.lead, g.members)}
    with _lock:
        items = _load()
        items.append(item)
        _save(items)
    return item


@router.patch("/{group_id}")
def update(group_id: str, g: GroupPatch):
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == group_id:
                it.update(_clean(g.name if g.name is not None else it["name"], g.lead or it["lead"],
                                 g.members if g.members is not None else it["members"]))
                _save(items)
                return it
    raise HTTPException(404, "group not found")


@router.delete("/{group_id}")
def delete(group_id: str):
    with _lock:
        items = _load()
        kept = [it for it in items if it["id"] != group_id]
        if len(kept) == len(items):
            raise HTTPException(404, "group not found")
        _save(kept)
    return {"deleted": group_id}
