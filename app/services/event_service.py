import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PHASE_DIRECTIONS, Phase, SensorEventType, VehicleType
from app.models.queue_entry import QueueEntry
from app.models.sensor_event import SensorEvent
from app.repositories import junction_repo, queue_repo, sensor_event_repo


@dataclass(frozen=True)
class ProcessResult:
    applied: bool
    queue_delta: int
    queue_count: int
    reason: str | None


class JunctionNotFound(Exception):
    pass


async def process_sensor_event(
    session: AsyncSession,
    *,
    junction_id: uuid.UUID,
    event_id: str,
    event_type: SensorEventType,
    direction: str,
    vehicle_type: str,
    occurred_at: datetime | None,
) -> ProcessResult:

    junction = await junction_repo.get_for_update(session, junction_id)
    if junction is None:
        raise JunctionNotFound(str(junction_id))

    existing = await sensor_event_repo.find_by_event_id(
        session, junction_id, event_id
    )
    if existing is not None:
        queue = await queue_repo.get(session, junction_id, direction, vehicle_type)
        current_count = queue.count if queue is not None else 0
        return ProcessResult(False, 0, current_count, "DUPLICATE")

    event = SensorEvent(
        junction_id=junction_id,
        event_id=event_id,
        event_type=event_type.value,
        direction=direction,
        vehicle_type=vehicle_type,
        occurred_at=occurred_at,
    )
    session.add(event)

    entry = await queue_repo.get_or_create(
        session, junction_id, direction, vehicle_type
    )
    reason: str | None = None

    if event_type is SensorEventType.VEHICLE_ARRIVED:
        if entry.count == 0:
            entry.oldest_arrival_at = datetime.now(timezone.utc)
        entry.count += 1
        event.queue_delta = 1
        applied = True

    elif event_type is SensorEventType.VEHICLE_CLEARED:
        if entry.count > 0:
            entry.count -= 1
            event.queue_delta = -1
            applied = True
            if entry.count == 0:
                entry.oldest_arrival_at = None
        else:
            event.queue_delta = 0
            event.anomaly = "CLEAR_WITHOUT_ARRIVAL"
            applied = False
            reason = "CLEAR_WITHOUT_ARRIVAL"

    else:
        raise ValueError(f"Unhandled event_type: {event_type}")

    if (
        event_type is SensorEventType.VEHICLE_CLEARED
        and vehicle_type == VehicleType.EMERGENCY.value
        and junction.mode == "EMERGENCY"
        and junction.desired_phase is not None
    ):
        remaining = await _emergency_queue_for_phase(
            session, junction_id, junction.desired_phase
        )
        if remaining == 0:
            from app.services import command_service
            await command_service.on_emergency_cleared(
                session, junction, Phase(junction.desired_phase)
            )

    await session.commit()

    return ProcessResult(
        applied=applied,
        queue_delta=event.queue_delta,
        queue_count=entry.count,
        reason=reason,
    )


async def _emergency_queue_for_phase(
    session: AsyncSession, junction_id, phase: str,
) -> int:
    directions = [d.value for d in PHASE_DIRECTIONS[Phase(phase)]]
    stmt = select(
        func.coalesce(func.sum(QueueEntry.count), 0)
    ).where(
        QueueEntry.junction_id == junction_id,
        QueueEntry.direction.in_(directions),
        QueueEntry.vehicle_type == VehicleType.EMERGENCY.value,
    )
    return int((await session.execute(stmt)).scalar_one())