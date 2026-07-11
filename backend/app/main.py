"""FastAPI app entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import config, db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Stock News Dashboard", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "missing_keys": config.missing_keys(),
    }
