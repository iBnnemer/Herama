from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import config
from app.api import memory, ollama, skills

app = FastAPI(title="Herama")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if config.API_KEY:
        token = request.headers.get("Authorization", "")
        if token not in (f"Bearer {config.API_KEY}", config.API_KEY):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


app.include_router(ollama.router)
app.include_router(memory.router)
app.include_router(skills.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
