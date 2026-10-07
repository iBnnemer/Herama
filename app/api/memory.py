from fastapi import APIRouter
from pydantic import BaseModel

from app.memory.store import memory

router = APIRouter(prefix="/api/memory")


class Fact(BaseModel):
    content: str
    kind: str = "fact"
    tags: str = ""
    agent: str = ""   # empty = shared by every agent


@router.post("")
def add(f: Fact):
    return {"id": memory.add(f.content, f.kind, f.tags, f.agent)}


@router.get("")
def recent(k: int = 20, agent: str | None = None):
    return memory.recent(k, agent)


@router.get("/search")
def search(q: str, k: int = 5, agent: str | None = None):
    return memory.search(q, k, agent)


@router.delete("/{fid}")
def delete(fid: int):
    memory.delete(fid)
    return {"ok": True}
