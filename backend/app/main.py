from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # startup/shutdown filled in later tasks

app = FastAPI(lifespan=lifespan)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
