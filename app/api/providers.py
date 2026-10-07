"""External model providers (OpenAI-compatible APIs): list, save, delete, test."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import remote

router = APIRouter(prefix="/api/providers")


class ProviderIn(BaseModel):
    id: str = ""
    label: str = ""
    provider: str = "Custom"
    model: str
    base_url: str
    api_key: str = ""


def _check(p: ProviderIn):
    if not p.model.strip():
        raise HTTPException(400, "model name is required")
    if not p.base_url.strip().startswith(("http://", "https://")):
        raise HTTPException(400, "the address must start with http:// or https://")


@router.get("")
def list_providers():
    return {"presets": remote.PRESETS, "items": [remote.public(p) for p in remote.load()]}


@router.post("")
def save(p: ProviderIn):
    _check(p)
    try:
        return remote.public(remote.upsert(p.model_dump()))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/test")
def test(p: ProviderIn):
    _check(p)
    d = p.model_dump()
    if not d["api_key"] and d["id"]:  # editing a saved entry: reuse its stored key
        d["api_key"] = next((x.get("api_key", "") for x in remote.load() if x["id"] == d["id"]), "")
    return remote.test(d)


@router.delete("/{pid}")
def delete(pid: str):
    if not remote.remove(pid):
        raise HTTPException(404, "not found")
    return {"ok": True}
