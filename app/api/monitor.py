from fastapi import APIRouter

from app import monitor
from app.engine import engine

router = APIRouter(prefix="/api/monitor")


@router.get("/state")
def state():
    """Cheap status used by the chat circle."""
    return monitor.state()


@router.get("")
def snapshot():
    ctx, experts = engine.monitor_info()
    return monitor.snapshot(ctx, experts)
