from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.graph_dep import get_ledger, get_uar
from api.persistence.projects_db import init_db
from api.routes import approvals, forks, locks, projects, runs
from api.routes.assets import router as assets_router
from api.routes.checkpoints import router as checkpoints_router
from api.routes.creative import router as creative_router
from api.routes.ot import router as ot_router
from api.routes.render import router as render_router
from api.settings import settings
from api.ws.broadcaster import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await get_uar().init()
    await get_ledger().init()
    yield


app = FastAPI(title="CinematicVideoCreator API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(runs.router, prefix="/projects", tags=["runs"])
app.include_router(approvals.router, prefix="/projects", tags=["approvals"])
app.include_router(locks.router, prefix="/projects", tags=["locks"])
app.include_router(forks.router, prefix="/projects", tags=["forks"])
app.include_router(creative_router, prefix="/projects", tags=["creative"])
app.include_router(assets_router, prefix="/projects", tags=["assets"])
app.include_router(render_router, prefix="/projects", tags=["render"])
app.include_router(ot_router, prefix="/projects", tags=["ot"])
app.include_router(checkpoints_router, prefix="/projects", tags=["checkpoints"])
app.include_router(ws_router)
