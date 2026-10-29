import uuid

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Direction, SignalState
from app.models.signal_reading import SignalReading


async def get_dict(
    session: AsyncSession, junction_id: uuid.UUID,
) -> dict[Direction, SignalState]:
    stmt = select(SignalReading).where(SignalReading.junction_id == junction_id)
    rows = (await session.execute(stmt)).scalars().all()
    result: dict[Direction, SignalState] = {
        d: SignalState.UNKNOWN for d in Direction
    }
    for row in rows:
        try:
            result[Direction(row.direction)] = SignalState(row.confirmed)
        except ValueError:
            continue
    return result


async def ensure_all_directions(
    session: AsyncSession, junction_id: uuid.UUID,
) -> None:
    """Ensure four rows exist, defaulting to UNKNOWN.
    
    Uses atomic INSERT ... ON CONFLICT DO NOTHING to prevent race conditions
    and deadlocks when multiple tests or requests try to initialize at once.
    """
    for d in Direction:
        stmt = (
            insert(SignalReading)
            .values(
                id=uuid.uuid4(),
                junction_id=junction_id,
                direction=d.value,
                confirmed=SignalState.UNKNOWN.value,
            )
            .on_conflict_do_nothing(
                index_elements=["junction_id", "direction"]
            )
        )
        await session.execute(stmt)
    await session.flush()


async def set_confirmed(
    session: AsyncSession,
    junction_id: uuid.UUID,
    direction: Direction,
    state: SignalState,
) -> None:
    """Update the confirmed lamp for one direction.
    
    Uses atomic UPSERT (INSERT ... ON CONFLICT DO UPDATE) to prevent
    deadlocks and race conditions.
    """
    stmt = (
        insert(SignalReading)
        .values(
            id=uuid.uuid4(),
            junction_id=junction_id,
            direction=direction.value,
            confirmed=state.value,
        )
        .on_conflict_do_update(
            index_elements=["junction_id", "direction"],
            set_={
                "confirmed": state.value,
                "updated_at": func.now()
            }
        )
    )
    await session.execute(stmt)
    await session.flush()