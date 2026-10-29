import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sensor_event import SensorEvent


async def find_by_event_id(
    session: AsyncSession, junction_id: uuid.UUID, event_id: str,
) -> SensorEvent | None:
    stmt = select(SensorEvent).where(
        SensorEvent.junction_id == junction_id,
        SensorEvent.event_id == event_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()