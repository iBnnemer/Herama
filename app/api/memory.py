from fastapi import APIRouter
from pydantic import BaseModel

from app.memory.store import memory

router = APIRouter(prefix="/api/memory")


class Fact(BaseModel):
    content: str
    kind: str = "fact"
    tags: str = ""


@router.post("")
def add(f: Fact):
    return {"id": memory.add(f.content, f.kind, f.tags)}


@router.get("")
def recent(k: int = 20):
    return memory.recent(k)


@router.get("/search")
def search(q: str, k: int = 5):
    return memory.search(q, k)


@router.delete("/{fid}")
def delete(fid: int):
    memory.delete(fid)
    return {"ok": True}
