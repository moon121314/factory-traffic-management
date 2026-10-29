import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import JunctionMode, LogicalState
from app.models.junction import Junction


async def create(session: AsyncSession, name: str) -> Junction:
    junction = Junction(name=name)
    junction.logical_state = LogicalState.ALL_RED.value
    junction.state_started_at = datetime.now(timezone.utc)
    junction.mode = JunctionMode.AUTO.value
    session.add(junction)
    await session.flush()
    return junction


async def get(session: AsyncSession, junction_id: uuid.UUID) -> Junction | None:
    return await session.get(Junction, junction_id)


async def get_for_update(
    session: AsyncSession, junction_id: uuid.UUID,
) -> Junction | None:
    stmt = (
        select(Junction)
        .where(Junction.id == junction_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[Junction]:
    stmt = select(Junction).order_by(Junction.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def list_all_for_update(session: AsyncSession) -> list[Junction]:
    stmt = select(Junction).with_for_update()
    return list((await session.execute(stmt)).scalars().all())