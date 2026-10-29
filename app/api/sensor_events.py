from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.sensor_event import SensorEventIn, SensorEventOut
from app.services import event_service

router = APIRouter(prefix="/api/sensor-events", tags=["sensor-events"])


@router.post("", response_model=SensorEventOut, status_code=status.HTTP_200_OK)
async def post_sensor_event(
    payload: SensorEventIn,
    session: AsyncSession = Depends(get_session),
) -> SensorEventOut:
    try:
        result = await event_service.process_sensor_event(
            session,
            junction_id=payload.junction_id,
            event_id=payload.event_id,
            event_type=payload.event_type,
            direction=payload.direction.value,
            vehicle_type=payload.vehicle_type.value,
            occurred_at=payload.occurred_at,
        )
    except event_service.JunctionNotFound as exc:
        raise HTTPException(404, f"Junction {exc} not found")

    return SensorEventOut(
        applied=result.applied,
        queue_delta=result.queue_delta,
        queue_count=result.queue_count,
        reason=result.reason,
    )