from fastapi import APIRouter
from pydantic import BaseModel

from app import tools

router = APIRouter(prefix="/api/tools")


class RunReq(BaseModel):
    name: str
    arguments: dict = {}
    dirs: list[str] = []


@router.get("")
def listing():
    return tools.listing()


@router.post("/run")
def run(r: RunReq):
    return tools.run(r.name, r.arguments, r.dirs)
