from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.controller.interface import Ack
from app.db import get_session
from app.domain.clock import SystemClock
from app.schemas.controller_event import ControllerEventIn, ControllerEventOut
from app.services import controller_service

router = APIRouter(prefix="/api/controller-events", tags=["controller"])


@router.post("", response_model=ControllerEventOut)
async def post_controller_event(
    payload: ControllerEventIn,
    session: AsyncSession = Depends(get_session),
) -> ControllerEventOut:
    ack = Ack(
        command_id=payload.command_id,
        accepted=payload.accepted,
        confirmed_signals=payload.signals,
        reason=payload.reason,
    )
    await controller_service.on_ack(session, ack, SystemClock())
    return ControllerEventOut(ok=True)