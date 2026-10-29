from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.command import CommandIn, CommandOut
from app.services import command_service

router = APIRouter(prefix="/api/junctions", tags=["commands"])


@router.post("/{junction_id}/commands", response_model=CommandOut)
async def post_command(
    junction_id: UUID,
    payload: CommandIn,
    session: AsyncSession = Depends(get_session),
) -> CommandOut:
    try:
        if payload.command_type == "MANUAL_GREEN_REQUEST":
            if payload.phase is None:
                raise HTTPException(422, "phase required")
            outcome = await command_service.request_manual_green(
                session, junction_id, payload.phase,
            )
        elif payload.command_type == "EMERGENCY_REQUEST":
            if payload.phase is None:
                raise HTTPException(422, "phase required")
            outcome = await command_service.request_emergency(
                session, junction_id, payload.phase,
            )
        elif payload.command_type == "RETURN_TO_AUTOMATIC":
            outcome = await command_service.return_to_automatic(
                session, junction_id,
            )
        else:
            raise HTTPException(422, "unknown command_type")
    except command_service.JunctionNotFound:
        raise HTTPException(404, "junction not found")
    except command_service.CommandRejected as e:
        raise HTTPException(409, str(e))

    return CommandOut(
        accepted=outcome.accepted,
        status=outcome.status,
        detail=outcome.detail,
    )