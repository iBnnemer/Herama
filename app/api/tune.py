"""Preliminary per-model settings for a chosen context length (nothing is applied here)."""
from fastapi import APIRouter, HTTPException

from app import tune
from app.engine import engine

router = APIRouter(prefix="/api/tune")


@router.get("")
def propose(model: str, ctx: int, ngl: int | None = None, cpu_moe: int | None = None, top_k: int | None = None):
    try:
        path = engine.path(model)
    except Exception:
        raise HTTPException(404, "model not found")
    return tune.propose(path, ctx, ngl, cpu_moe, top_k)
