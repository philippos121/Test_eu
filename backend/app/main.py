import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers import admin, auth, cases, chat, documents

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.generated_forms_dir, exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title="EU-Bagatellverfahren Portal",
    description="Portal für geringfügige Forderungen innerhalb der EU (VO 861/2007)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
