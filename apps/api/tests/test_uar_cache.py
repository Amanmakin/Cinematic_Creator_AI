"""Test UAR cache hit / cache miss / locked-layer behavior (no network)."""

import asyncio
import os
import tempfile

import pytest

from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload


# ---------------------------------------------------------------------------
# Fake adapter — never actually calls Replicate
# ---------------------------------------------------------------------------
class _FakeAdapter:
    name = "fake"
    version = "1.0.0"
    call_count = 0

    def supports(self, intent: CreativeIntent) -> bool:
        return True

    def translate(self, intent: CreativeIntent, ctx) -> ProviderPayload:
        return ProviderPayload(
            model="fake-model",
            inputs={"prompt": intent.parameters.get("prompt", ""), "seed": intent.seed},
            adapter_hint="fake",
            estimated_tokens=10,
        )

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        self.__class__.call_count += 1
        import hashlib, json
        h = hashlib.sha256(json.dumps(payload.inputs, sort_keys=True).encode()).hexdigest()
        return AssetRef(asset_id=h[:16], adapter=self.name, adapter_version=self.version)

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return payload.estimated_tokens


class _Ctx:
    def __init__(self, project_id: str, uar_root: str):
        self.project_id = project_id
        self.uar_root = uar_root


@pytest.fixture()
def tmp_store(tmp_path):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
    from api.uar.store import UARStore
    db = str(tmp_path / "test.sqlite")
    store = UARStore(db_path=db, uar_root=str(tmp_path / "uar"))
    asyncio.run(store.init())
    return store, db, str(tmp_path / "uar")


def _make_intent(seed: int = 42) -> CreativeIntent:
    return CreativeIntent(
        kind="generate_subject",
        target_path="scene.subjects[0]",
        parameters={"prompt": "a knight in shining armor"},
        seed=seed,
    )


def test_cache_miss_then_hit(tmp_store):
    store, db, uar_root = tmp_store
    adapter = _FakeAdapter()
    adapter.__class__.call_count = 0
    ctx = _Ctx("proj-1", uar_root)
    intent = _make_intent()

    asset1, cached1 = asyncio.run(
        store.get_or_create(intent, adapter, ctx, locked_paths=set())
    )
    assert not cached1, "first call should be a cache miss"
    assert adapter.call_count == 1

    asset2, cached2 = asyncio.run(
        store.get_or_create(intent, adapter, ctx, locked_paths=set())
    )
    assert cached2, "second identical call should be a cache hit"
    assert adapter.call_count == 1, "adapter.execute must not be called again"
    assert asset1.id == asset2.id


def test_locked_path_returns_existing(tmp_store):
    store, db, uar_root = tmp_store
    adapter = _FakeAdapter()
    adapter.__class__.call_count = 0
    ctx = _Ctx("proj-2", uar_root)
    intent = _make_intent()

    # First generate so the asset exists in store
    asset_orig, _ = asyncio.run(
        store.get_or_create(intent, adapter, ctx, locked_paths=set())
    )
    count_after_first = adapter.call_count

    # Now call with the path locked — should return the same asset without re-generating
    locked = {"scene.subjects[0]"}
    asset_locked, was_cached = asyncio.run(
        store.get_or_create(intent, adapter, ctx, locked_paths=locked)
    )
    assert was_cached
    assert adapter.call_count == count_after_first, "locked path must skip adapter.execute"
    assert asset_locked.id == asset_orig.id


def test_different_seeds_produce_different_assets(tmp_store):
    store, db, uar_root = tmp_store
    adapter = _FakeAdapter()
    ctx = _Ctx("proj-3", uar_root)

    intent_a = _make_intent(seed=1)
    intent_b = _make_intent(seed=2)

    asset_a, cached_a = asyncio.run(
        store.get_or_create(intent_a, adapter, ctx, locked_paths=set())
    )
    asset_b, cached_b = asyncio.run(
        store.get_or_create(intent_b, adapter, ctx, locked_paths=set())
    )

    assert not cached_a
    assert not cached_b
    assert asset_a.id != asset_b.id
