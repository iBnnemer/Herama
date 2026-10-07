"""Ollama-compatible routes."""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import resources
from app.engine import engine
from app.memory.store import memory

log = logging.getLogger("herama")
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


class ShowReq(BaseModel):
    name: str
    verbose: bool = False


@router.post("/show")
def show(r: ShowReq):
    try:
        p = engine.path(r.name)
    except FileNotFoundError:
        raise HTTPException(404, f"model '{r.name}' not found")
    st = p.stat()
    try:
        meta = resources.gguf_meta(p)
    except Exception:
        meta = {}
    return {
        "model": r.name,
        "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        "size": st.st_size,
        "details": {
            "format": "gguf",
            "parameter_size": str(meta.get("block_count", "")),
            "context_length": meta.get("context_length", 0),
            "embedding_length": meta.get("embedding_length", 0),
        },
        "model_info": meta if r.verbose else {},
    }


@router.get("/ps")
def ps():
    info = engine.ps()
    if not info:
        return {"models": []}
    return {"models": [{
        "name": f"{info['name']}:latest",
        "model": f"{info['model']}:latest",
        "size": 0,
        "digest": "",
        "details": {"format": "gguf"},
        "expires_at": "",
        "size_vram": info["n_gpu_layers"],
    }]}


class GenReq(BaseModel):
    model: str
    prompt: str = ""
    system: str | None = None
    stream: bool = True
    raw: bool = False
    options: dict = {}
    memory: bool = False       # inject recalled facts
    auto_extract: bool = False  # save response sentences as facts


class ChatReq(BaseModel):
    model: str
    messages: list[dict] = []
    tools: list[dict] = []
    stream: bool = True
    options: dict = {}
    memory: bool = False
    auto_extract: bool = False
    agent: str = ""            # whose memory to use: its own facts plus the shared ones


def _build(r: GenReq) -> str:
    sys = r.system or ""
    if r.memory and r.prompt:
        facts = memory.search(r.prompt)
        if facts:
            sys += "\nKnown facts:\n" + "\n".join(f"- #{f['id']} {f['content']}" for f in facts)
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
        memory.log_turn(r.model, r.prompt, text, auto_extract=r.auto_extract)
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
        try:
            for item in gen:
                if isinstance(item, str):
                    buf.append(item)
                    yield json.dumps({"model": r.model, "created_at": _now(), "response": item, "done": False}) + "\n"
                else:
                    yield json.dumps(final(item, "".join(buf))) + "\n"
        except Exception as e:
            log.exception("generation failed")
            yield json.dumps({"error": f"{type(e).__name__}: {e}", "done": True}) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


def _inject_memory(messages: list[dict], query: str, agent: str | None = None) -> list[dict]:
    """Prepend a system message with recalled facts if any match."""
    facts = memory.relevant(query, agent=agent)
    if not facts:
        return messages
    block = "Known facts:\n" + "\n".join(f"- #{f['id']} {f['content']}" for f in facts)
    if messages and messages[0].get("role") == "system":
        msgs = list(messages)
        msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n" + block}
        return msgs
    return [{"role": "system", "content": block}] + list(messages)


def _to_openai(messages: list[dict]) -> list[dict]:
    """Ollama-style {"images": [base64]} messages -> OpenAI content parts."""
    out = []
    for m in messages:
        imgs = m.get("images") or []
        if not imgs:
            out.append({k: v for k, v in m.items() if k != "images"})
            continue
        parts = [{"type": "text", "text": m.get("content", "")}]
        for b in imgs:
            url = b if b.startswith("data:") else f"data:image/jpeg;base64,{b}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        out.append({"role": m.get("role", "user"), "content": parts})
    return out


@router.post("/chat")
def chat(r: ChatReq):
    try:
        engine.path(r.model)
    except FileNotFoundError:
        raise HTTPException(404, f"model '{r.model}' not found")

    t0 = time.perf_counter_ns()
    last_user = next((m["content"] for m in reversed(r.messages) if m.get("role") == "user"), "")
    msgs = _inject_memory(r.messages, last_user, r.agent or None) if r.memory and last_user else r.messages
    has_images = any(m.get("images") for m in msgs)
    opts = {**r.options, "tools": r.tools} if r.tools else r.options
    gen = engine.chat(r.model, _to_openai(msgs), opts, r.stream, vision=has_images)

    def _msg(text: str) -> dict:
        return {"role": "assistant", "content": text}

    def final(raw, text):
        memory.log_turn(r.model, last_user, text, auto_extract=r.auto_extract)
        u = (raw or {}).get("usage", {})
        choice = ((raw or {}).get("choices") or [{}])[0]
        fr = choice.get("finish_reason") or "stop"
        calls = (raw or {}).get("tool_calls") or (choice.get("message") or {}).get("tool_calls")
        msg = _msg("" if r.stream else text)
        if calls:
            msg["tool_calls"] = calls
            fr = "tool_calls"
        return {"model": r.model, "created_at": _now(),
                "message": msg,
                "done": True, "done_reason": fr,
                "total_duration": time.perf_counter_ns() - t0,
                "prompt_eval_count": u.get("prompt_tokens", 0),
                "eval_count": u.get("completion_tokens", 0)}

    if not r.stream:
        text = next(gen)
        return final(next(gen, None), text)

    def ndjson():
        buf = []
        try:
            for item in gen:
                if isinstance(item, str):
                    buf.append(item)
                    yield json.dumps({"model": r.model, "created_at": _now(),
                                      "message": _msg(item), "done": False}) + "\n"
                else:
                    yield json.dumps(final(item, "".join(buf))) + "\n"
        except Exception as e:
            log.exception("chat failed")
            yield json.dumps({"error": f"{type(e).__name__}: {e}", "done": True}) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


# ── model management ──────────────────────────────────────────────────────────

class DeleteReq(BaseModel):
    name: str


class CopyReq(BaseModel):
    source: str
    destination: str


class PullReq(BaseModel):
    name: str
    stream: bool = True


class EmbedReq(BaseModel):
    model: str
    prompt: str
    options: dict = {}


@router.delete("/delete")
def delete_model(r: DeleteReq):
    try:
        p = engine.path(r.name)
    except FileNotFoundError:
        raise HTTPException(404, f"model '{r.name}' not found")
    if engine._loaded_name and r.name in (engine._loaded_name, f"{engine._loaded_name}:latest"):
        engine.unload()
    p.unlink()
    return {"status": "success"}


@router.post("/copy")
def copy_model(r: CopyReq):
    import shutil
    try:
        src = engine.path(r.source)
    except FileNotFoundError:
        raise HTTPException(404, f"source '{r.source}' not found")
    dest_name = r.destination.split(":")[0]
    dest = src.parent / f"{dest_name}.gguf"
    if dest.exists():
        raise HTTPException(400, f"destination '{r.destination}' already exists")
    shutil.copy2(src, dest)
    return {"status": "success"}


@router.post("/pull")
def pull(r: PullReq):
    """Stub — Herama uses local GGUF files; place them in models/ manually."""
    msg = f"Herama does not download models. Place '{r.name}.gguf' in the models/ directory."
    if not r.stream:
        return {"status": "error", "error": msg}

    def _stream():
        yield json.dumps({"status": msg, "completed": 0, "total": 0}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.post("/embeddings")
def embeddings(r: EmbedReq):
    try:
        engine.path(r.model)
    except FileNotFoundError:
        raise HTTPException(404, f"model '{r.model}' not found")
    from app import config as _cfg
    llm = engine.load(r.model, r.options.get("num_ctx"), r.options.get("num_gpu"),
                      keep_alive=r.options.get("keep_alive", 300))
    vec = llm.create_embedding(r.prompt)
    data = vec.get("data", [{}])
    embedding = data[0].get("embedding", []) if data else []
    return {"embedding": embedding}
