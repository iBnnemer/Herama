from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine import engine
from app.skills import registry

router = APIRouter(prefix="/api/skills")


class GenSkill(BaseModel):
    model: str
    name: str
    task: str


class SaveSkill(BaseModel):
    name: str
    code: str
    desc: str = ""


def _wrap(fn, *a):
    try:
        return fn(*a)
    except (registry.SkillError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_():
    return registry.list_skills()


@router.post("/generate")
def generate(r: GenSkill):
    return _wrap(registry.generate, engine, r.model, r.name, r.task)


@router.post("")
def save(r: SaveSkill):
    return _wrap(registry.save, r.name, r.code, r.desc)


@router.post("/{name}/run")
def run(name: str, args: dict | None = None):
    return {"result": _wrap(registry.run, name, args or {})}
