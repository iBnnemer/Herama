import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from app.api import agents, groups, hub, memory, monitor, ollama, skills, tools, tune

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("herama")

app = FastAPI(title="Herama")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if config.API_KEY:
        token = request.headers.get("Authorization", "")
        if token not in (f"Bearer {config.API_KEY}", config.API_KEY):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def log_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    log.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, ms)
    return response


def _engine_info() -> dict:
    from app import runtime
    text, accelerated = runtime.label()
    if text:
        return {"engine": text, "accelerated": accelerated, "runtime": runtime.status()}
    try:  # no llama.cpp runtime: report the llama-cpp-python build instead
        import llama_cpp
        gpu = bool(llama_cpp.llama_supports_gpu_offload())
        return {"engine": "llama-cpp-python " + ("GPU" if gpu else "CPU only"), "accelerated": gpu,
                "runtime": runtime.status()}
    except Exception:
        return {"runtime": runtime.status()}


@app.get("/health")
def health():
    from app.engine import engine
    loaded = engine.ps()
    return {
        "status": "ok",
        "model": loaded["name"] if loaded else None,
        "models_available": len(list(config.MODELS_DIR.glob("**/*.gguf"))),
        **_engine_info(),
    }


app.include_router(ollama.router)
app.include_router(memory.router)
app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(groups.router)
app.include_router(hub.router)
app.include_router(tune.router)
app.include_router(monitor.router)
app.include_router(tools.router)


@app.get("/api/runtime")
def runtime_status():
    from app import runtime
    return {**runtime.status(), "installed": runtime.current_backend()}


@app.post("/api/runtime/retry")
def runtime_retry():
    from app import runtime
    runtime.start_background()
    return runtime.status()


@app.on_event("startup")
def _prepare_runtime():
    from app import runtime
    if not runtime.disabled() and "PYTEST_CURRENT_TEST" not in __import__("os").environ:
        runtime.kill_stale()  # orphans from a previous run would hold GPU memory
    runtime.start_background()

# added last so it is the outermost layer and answers preflight before auth
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def main():
    import uvicorn

    if config.PRELOAD:
        from app.engine import engine as _eng
        try:
            log.info("preloading %s", config.PRELOAD)
            _eng.load(config.PRELOAD, keep_alive=-1)
            log.info("preloaded %s", config.PRELOAD)
        except Exception as e:
            log.warning("preload failed: %s", e)

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    import uvicorn

    if config.PRELOAD:
        from app.engine import engine
        try:
            log.info("preloading %s", config.PRELOAD)
            engine.load(config.PRELOAD, keep_alive=-1)
            log.info("preloaded %s", config.PRELOAD)
        except Exception as e:
            log.warning("preload failed: %s", e)

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
