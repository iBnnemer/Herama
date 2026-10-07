"""External models reached over an OpenAI-compatible HTTP API (OpenAI, OpenRouter, Groq, DeepSeek, ...)."""
import json
import threading
import urllib.error
import urllib.request
import uuid

from app import config

PREFIX = "api:"
PRESETS = {
    "OpenAI": "https://api.openai.com/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "Together": "https://api.together.xyz/v1",
    "Gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "Anthropic": "https://api.anthropic.com/v1",
    "Custom": "",
}
_lock = threading.Lock()


def _file():
    return config.MEMORY_DIR / "providers.json"


def load() -> list[dict]:
    try:
        d = json.loads(_file().read_text("utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(items, indent=1), "utf-8")


def public(p: dict) -> dict:
    """Entry without the secret: only whether a key exists and its last characters."""
    key = p.get("api_key", "")
    return {**{k: v for k, v in p.items() if k != "api_key"}, "has_key": bool(key), "key_hint": key[-4:] if len(key) > 8 else ""}


def upsert(data: dict) -> dict:
    with _lock:
        items = load()
        cur = next((p for p in items if p["id"] == data.get("id")), None)
        entry = {"id": cur["id"] if cur else uuid.uuid4().hex[:8], "provider": data.get("provider", "Custom"),
                 "model": data["model"].strip(), "base_url": data["base_url"].strip().rstrip("/"),
                 "api_key": (data.get("api_key") or "").strip() or (cur or {}).get("api_key", "")}
        label = (data.get("label") or "").strip() or f"{entry['provider']} {entry['model']}"
        entry["label"] = label
        if any(p["label"] == label and p["id"] != entry["id"] for p in items):
            raise ValueError("a model with this name already exists")
        items = [entry if p["id"] == entry["id"] else p for p in items] if cur else items + [entry]
        _save(items)
        return entry


def remove(pid: str) -> bool:
    with _lock:
        items = load()
        rest = [p for p in items if p["id"] != pid]
        _save(rest)
        return len(rest) != len(items)


def names() -> list[str]:
    return [PREFIX + p["label"] for p in load()]


def find(name: str) -> dict | None:
    return next((p for p in load() if name.startswith(PREFIX) and p["label"] == name[len(PREFIX):].removesuffix(":latest")), None)


def is_remote(name: str) -> bool:
    return find(name) is not None


def _request(p: dict, body: dict, timeout):
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "herama/1.0"}
    if p.get("api_key"):
        headers["Authorization"] = f"Bearer {p['api_key']}"
    req = urllib.request.Request(f"{p['base_url']}/chat/completions", data=json.dumps(body).encode(), headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{p['provider']} answered {e.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"cannot reach {p['base_url']}: {getattr(e, 'reason', e)}") from None


def test(p: dict) -> dict:
    """One tiny request to check the address, the key and the model name."""
    try:
        with _request(p, {"model": p["model"], "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}, 30) as r:
            d = json.load(r)
        return {"ok": True, "detail": (d.get("choices") or [{}])[0].get("message", {}).get("content", "") or "ok"}
    except Exception as e:
        return {"ok": False, "detail": str(e).replace(p.get("api_key") or "\0", "***")}


def chat(p: dict, messages: list[dict], opts: dict, stream: bool):
    """Same contract as Engine.chat: yields text pieces, then one final dict (usage, tool_calls)."""
    body = {"model": p["model"], "messages": messages, "stream": stream}
    for src, dst in (("temperature", "temperature"), ("top_p", "top_p"), ("num_predict", "max_tokens")):
        if opts.get(src) is not None and not (src == "num_predict" and opts[src] < 0):
            body[dst] = opts[src]
    if opts.get("tools"):
        body["tools"] = opts["tools"]
    if stream:
        body["stream_options"] = {"include_usage": True}
    try:
        resp = _request(p, body, 600)
    except RuntimeError as e:
        raise RuntimeError(str(e).replace(p.get("api_key") or "\0", "***")) from None
    with resp:
        if not stream:
            r = json.load(resp)
            msg = r["choices"][0]["message"]
            yield msg.get("content") or ""
            yield r
            return
        last, usage, thinking, calls = None, None, False, {}
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if obj.get("error"):
                raise RuntimeError(str(obj["error"])[:300])
            if obj.get("usage"):
                usage = obj["usage"]
            if not obj.get("choices"):
                continue
            last = obj
            delta = obj["choices"][0].get("delta") or {}
            for tc in delta.get("tool_calls") or []:
                cur = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": ""})
                cur["id"] = tc.get("id") or cur["id"]
                fn = tc.get("function") or {}
                cur["name"] += fn.get("name") or ""
                cur["arguments"] += fn.get("arguments") or ""
            think = delta.get("reasoning_content")
            text = delta.get("content") or ""
            if think:
                yield ("" if thinking else "<think>") + think
                thinking = True
            if text:
                yield ("</think>\n" if thinking else "") + text
                thinking = False
        last = last or {}
        if usage:
            last["usage"] = usage
        if calls:
            last["tool_calls"] = [{"id": c["id"] or f"call_{i}", "type": "function",
                                   "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                  for i, c in sorted(calls.items())]
        yield last
