import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env before any LLM client is constructed

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dag.reducers import init_dag_tables
from api.graph_dep import get_ledger, get_uar
from api.memory import compressed as compressed_mod
from api.memory import retrieval as retrieval_mod
from api.memory import uar as uar_mod
from api.persistence.projects_db import init_db
from api.routes import approvals, forks, locks, projects, runs
from api.routes.assets import router as assets_router
from api.routes.cancel import router as cancel_router
from api.routes.checkpoints import router as checkpoints_router
from api.routes.creative import router as creative_router
from api.routes.ot import router as ot_router
from api.routes.render import router as render_router
from api.routes.generation_settings import router as generation_settings_router
from api.routes.llm_settings import router as llm_settings_router
from api.routes.llm_settings import load_and_apply_saved as llm_load_and_apply
from api.routes.style import router as style_router
from api.settings import settings
from api.ws.broadcaster import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_dag_tables()
    await get_uar().init()
    await get_ledger().init()
    await uar_mod.migrate()
    await retrieval_mod.init_tables()
    await compressed_mod.init_table()
    await llm_load_and_apply()
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
app.include_router(cancel_router, prefix="/projects", tags=["cancel"])
app.include_router(ot_router, prefix="/projects", tags=["ot"])
app.include_router(checkpoints_router, prefix="/projects", tags=["checkpoints"])
app.include_router(style_router, prefix="/projects", tags=["style"])
app.include_router(generation_settings_router, prefix="/projects", tags=["generation"])
app.include_router(llm_settings_router, tags=["llm"])
app.include_router(ws_router)
