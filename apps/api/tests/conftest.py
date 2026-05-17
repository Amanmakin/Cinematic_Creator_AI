import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use a temp DB so tests are isolated
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
os.environ["DB_PATH"] = _tmp.name
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


@pytest_asyncio.fixture()
async def client():
    # Import app after env vars are set
    from api.main import app
    from api.persistence.projects_db import init_db

    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


SAMPLE_CANON = {
    "aspect_ratio": "16:9",
    "duration_seconds_max": 30.0,
    "aesthetic_tags": ["cinematic"],
    "style_guide": "",
    "banned_terms": [],
}
