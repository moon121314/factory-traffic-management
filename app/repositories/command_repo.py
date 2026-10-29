from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import Command


async def record(
    session: AsyncSession,
    *,
    junction_id,
    command_type: str,
    phase: str | None,
    status: str,
    detail: str | None = None,
) -> Command:
    cmd = Command(
        junction_id=junction_id,
        command_type=command_type,
        phase=phase,
        status=status,
        detail=detail,
    )
    session.add(cmd)
    return cmd