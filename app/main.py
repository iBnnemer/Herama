from fastapi import FastAPI

from app import config
from app.api import memory, ollama, skills

app = FastAPI(title="Herama")
app.include_router(ollama.router)
app.include_router(memory.router)
app.include_router(skills.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
