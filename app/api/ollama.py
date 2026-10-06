"""Ollama-compatible routes."""
import hashlib
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.engine import engine
from app.memory.store import memory

router = APIRouter(prefix="/api")


def _now():
    return datetime.now(timezone.utc).isoformat()


@router.get("/tags")
def tags():
    out = []
    for p in engine.models():
        st = p.stat()
        out.append({
            "name": f"{p.stem}:latest", "model": f"{p.stem}:latest",
            "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "size": st.st_size,
            "digest": hashlib.sha256(f"{p}{st.st_mtime}".encode()).hexdigest(),
            "details": {"format": "gguf", "family": "", "parameter_size": "", "quantization_level": ""},
        })
    return {"models": out}


@router.get("/version")
def version():
    return {"version": "0.1.0-herama"}


class GenReq(BaseModel):
    model: str
    prompt: str = ""
    system: str | None = None
    stream: bool = True
    raw: bool = False
    options: dict = {}
    memory: bool = False  # Herama extension: inject recalled facts


def _build(r: GenReq) -> str:
    sys = r.system or ""
    if r.memory and r.prompt:
        facts = memory.search(r.prompt)
        if facts:
            sys += "\nKnown facts:\n" + "\n".join(f"- {f['content']}" for f in facts)
    if r.raw or not sys.strip():
        return r.prompt
    return f"{sys.strip()}\n\n{r.prompt}"


@router.post("/generate")
def generate(r: GenReq):
    try:
        engine.path(r.model)
    except FileNotFoundError:
        raise HTTPException(404, f"model '{r.model}' not found")
    if not r.prompt:  # Ollama: empty prompt = load model only
        engine.load(r.model)
        return {"model": r.model, "created_at": _now(), "response": "", "done": True, "done_reason": "load"}

    t0 = time.perf_counter_ns()
    gen = engine.generate(r.model, _build(r), r.options, r.stream)

    def final(raw, text):
        memory.log_turn(r.model, r.prompt, text)
        u = (raw or {}).get("usage", {})
        fr = ((raw or {}).get("choices") or [{}])[0].get("finish_reason") or "stop"
        return {"model": r.model, "created_at": _now(), "response": "" if r.stream else text,
                "done": True, "done_reason": fr, "context": [],
                "total_duration": time.perf_counter_ns() - t0,
                "prompt_eval_count": u.get("prompt_tokens", 0), "eval_count": u.get("completion_tokens", 0)}

    if not r.stream:
        text = next(gen)
        return final(next(gen, None), text)

    def ndjson():
        buf = []
        for item in gen:
            if isinstance(item, str):
                buf.append(item)
                yield json.dumps({"model": r.model, "created_at": _now(), "response": item, "done": False}) + "\n"
            else:
                yield json.dumps(final(item, "".join(buf))) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")
