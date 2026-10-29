import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_entry import QueueEntry


async def get(
    session: AsyncSession,
    junction_id: uuid.UUID,
    direction: str,
    vehicle_type: str,
) -> QueueEntry | None:
    stmt = select(QueueEntry).where(
        QueueEntry.junction_id == junction_id,
        QueueEntry.direction == direction,
        QueueEntry.vehicle_type == vehicle_type,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_create(
    session: AsyncSession,
    junction_id: uuid.UUID,
    direction: str,
    vehicle_type: str,
) -> QueueEntry:
    existing = await get(session, junction_id, direction, vehicle_type)
    if existing is not None:
        return existing
    entry = QueueEntry(
        junction_id=junction_id,
        direction=direction,
        vehicle_type=vehicle_type,
        count=0,
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_for_junction(
    session: AsyncSession, junction_id: uuid.UUID,
) -> list[QueueEntry]:
    stmt = select(QueueEntry).where(QueueEntry.junction_id == junction_id)
    return list((await session.execute(stmt)).scalars().all())