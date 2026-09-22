"""Durable, atomic budget reservations shared by a root run and its workers."""
from contextvars import ContextVar
from sqlalchemy import update, select

root_budget_id: ContextVar[str | None] = ContextVar("root_budget_id", default=None)
request_scope: ContextVar[dict | None] = ContextVar("request_scope", default=None)


class BudgetExceeded(ValueError):
    pass


async def create_budget(run_id: str, limit: int):
    from core.memory.database import async_session
    from core.memory.models import RunTokenBudget
    async with async_session() as db:
        db.add(RunTokenBudget(id=run_id, token_limit=limit, spent=0, reserved=0))
        await db.commit()


async def reserve(run_id: str, call_id: str, amount: int):
    from core.memory.database import async_session
    from core.memory.models import RunTokenBudget, TokenReservation
    if amount < 0:
        raise ValueError("Negative reservation")
    async with async_session() as db:
        result = await db.execute(update(RunTokenBudget).where(
            RunTokenBudget.id == run_id,
            RunTokenBudget.spent + RunTokenBudget.reserved + amount <= RunTokenBudget.token_limit,
        ).values(reserved=RunTokenBudget.reserved + amount))
        if result.rowcount != 1:
            raise BudgetExceeded("Shared task token budget exhausted; completion is unverified.")
        db.add(TokenReservation(id=call_id, run_id=run_id, amount=amount, settled=False))
        await db.commit()


async def settle(call_id: str, actual: int | None):
    from core.memory.database import async_session
    from core.memory.models import RunTokenBudget, TokenReservation
    async with async_session() as db:
        reservation = await db.scalar(select(TokenReservation).where(TokenReservation.id == call_id))
        if reservation is None:
            return
        claimed = await db.execute(update(TokenReservation).where(
            TokenReservation.id == call_id, TokenReservation.settled.is_(False)
        ).values(settled=True))
        if claimed.rowcount != 1:
            return
        used = actual if isinstance(actual, int) and not isinstance(actual, bool) and actual >= 0 else reservation.amount
        await db.execute(update(RunTokenBudget).where(RunTokenBudget.id == reservation.run_id).values(
            reserved=RunTokenBudget.reserved - reservation.amount,
            spent=RunTokenBudget.spent + used))
        await db.commit()
