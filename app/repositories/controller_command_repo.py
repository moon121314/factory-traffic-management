import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ControllerCommandStatus
from app.models.controller_command import ControllerCommand


async def create(
    session: AsyncSession,
    *,
    junction_id: uuid.UUID,
    command_id: str,
    target_json: str,
) -> ControllerCommand:
    cmd = ControllerCommand(
        junction_id=junction_id,
        command_id=command_id,
        target=target_json,
        status=ControllerCommandStatus.PENDING.value,
    )
    session.add(cmd)
    await session.flush()
    return cmd


async def find_inflight(
    session: AsyncSession, junction_id: uuid.UUID,
) -> ControllerCommand | None:
    stmt = select(ControllerCommand).where(
        ControllerCommand.junction_id == junction_id,
        ControllerCommand.status.in_([
            ControllerCommandStatus.PENDING.value,
            ControllerCommandStatus.SENT.value,
        ]),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_by_command_id(
    session: AsyncSession, command_id: str,
) -> ControllerCommand | None:
    stmt = select(ControllerCommand).where(
        ControllerCommand.command_id == command_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_overdue(
    session: AsyncSession, cutoff: datetime,
) -> list[ControllerCommand]:
    stmt = select(ControllerCommand).where(
        ControllerCommand.status == ControllerCommandStatus.SENT.value,
        ControllerCommand.sent_at < cutoff,
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_sent(
    session: AsyncSession, cmd_id: uuid.UUID, sent_at: datetime,
) -> None:
    cmd = await session.get(ControllerCommand, cmd_id)
    if cmd is None:
        return
    cmd.status = ControllerCommandStatus.SENT.value
    cmd.sent_at = sent_at


async def mark_acked(
    session: AsyncSession, cmd_id: uuid.UUID, acked_at: datetime,
) -> None:
    cmd = await session.get(ControllerCommand, cmd_id)
    if cmd is None:
        return
    cmd.status = ControllerCommandStatus.ACKED.value
    cmd.acked_at = acked_at


async def mark_rejected(
    session: AsyncSession, cmd_id: uuid.UUID, reason: str,
) -> None:
    cmd = await session.get(ControllerCommand, cmd_id)
    if cmd is None:
        return
    cmd.status = ControllerCommandStatus.REJECTED.value
    cmd.error = reason[:500]


async def mark_timeout(session: AsyncSession, cmd_id: uuid.UUID) -> None:
    cmd = await session.get(ControllerCommand, cmd_id)
    if cmd is None:
        return
    cmd.status = ControllerCommandStatus.TIMEOUT.value


async def mark_failed(
    session: AsyncSession, cmd_id: uuid.UUID, reason: str,
) -> None:
    cmd = await session.get(ControllerCommand, cmd_id)
    if cmd is None:
        return
    cmd.status = ControllerCommandStatus.FAILED.value
    cmd.error = reason[:500]


async def count_recent_failures(
    session: AsyncSession, junction_id: uuid.UUID, limit: int,
) -> int:
    stmt = (
        select(ControllerCommand)
        .where(ControllerCommand.junction_id == junction_id)
        .order_by(ControllerCommand.created_at.desc())
        .limit(limit)
    )
    recent = list((await session.execute(stmt)).scalars().all())
    count = 0
    for cmd in recent:
        if cmd.status in (
            ControllerCommandStatus.TIMEOUT.value,
            ControllerCommandStatus.FAILED.value,
        ):
            count += 1
        else:
            break
    return count


async def list_for_junction(
    session: AsyncSession, junction_id: uuid.UUID,
) -> list[ControllerCommand]:
    stmt = (
        select(ControllerCommand)
        .where(ControllerCommand.junction_id == junction_id)
        .order_by(ControllerCommand.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())