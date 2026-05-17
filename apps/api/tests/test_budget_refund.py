"""Test that a failed task refunds the reserved budget back to the ledger."""

import os
import tempfile

import pytest

os.environ.setdefault("DB_PATH", tempfile.mktemp(suffix=".sqlite"))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_budget.sqlite")


@pytest.mark.asyncio
async def test_reserve_then_refund_restores_balance(db_path):
    from api.orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj1", cap=1000)

    assert await ledger.remaining("proj1") == 1000

    rid = await ledger.reserve("proj1", 500)
    assert await ledger.remaining("proj1") == 500

    await ledger.refund("proj1", rid)
    assert await ledger.remaining("proj1") == 1000


@pytest.mark.asyncio
async def test_reserve_then_commit_consumes_balance(db_path):
    from api.orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj2", cap=1000)

    rid = await ledger.reserve("proj2", 300)
    await ledger.commit("proj2", rid, 300)

    assert await ledger.remaining("proj2") == 700


@pytest.mark.asyncio
async def test_budget_exceeded_raises(db_path):
    from api.orchestrator.budget import BudgetExceeded, BudgetLedger

    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj3", cap=100)

    with pytest.raises(BudgetExceeded):
        await ledger.reserve("proj3", 200)


@pytest.mark.asyncio
async def test_double_refund_is_idempotent(db_path):
    from api.orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj4", cap=1000)

    rid = await ledger.reserve("proj4", 400)
    await ledger.refund("proj4", rid)
    await ledger.refund("proj4", rid)  # second refund should be no-op

    assert await ledger.remaining("proj4") == 1000


@pytest.mark.asyncio
async def test_spend_refunds_on_exception(db_path):
    from api.orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj5", cap=1000)

    async def failing_fn():
        raise ValueError("intentional failure")

    with pytest.raises(ValueError):
        await ledger.spend("proj5", 500, failing_fn)

    assert await ledger.remaining("proj5") == 1000
