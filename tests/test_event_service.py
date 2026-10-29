import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.enums import SensorEventType
from app.models.queue_entry import QueueEntry
from app.models.sensor_event import SensorEvent
from app.services.event_service import JunctionNotFound, process_sensor_event


async def _make_junction(session, name="j1"):
    from app.repositories import junction_repo
    j = await junction_repo.create(session, name)
    await session.commit()
    return j


async def _arrive(session, jid, *, event_id=None, direction="NORTH", vehicle_type="TRUCK"):
    return await process_sensor_event(
        session, junction_id=jid,
        event_id=event_id or str(uuid.uuid4()),
        event_type=SensorEventType.VEHICLE_ARRIVED,
        direction=direction, vehicle_type=vehicle_type, occurred_at=None,
    )


async def _clear(session, jid, *, event_id=None, direction="NORTH", vehicle_type="TRUCK"):
    return await process_sensor_event(
        session, junction_id=jid,
        event_id=event_id or str(uuid.uuid4()),
        event_type=SensorEventType.VEHICLE_CLEARED,
        direction=direction, vehicle_type=vehicle_type, occurred_at=None,
    )


async def test_arrival_increments_queue(session):
    j = await _make_junction(session)
    r = await _arrive(session, j.id)
    assert r.applied is True
    assert r.queue_delta == 1
    assert r.queue_count == 1


async def test_clear_decrements_queue(session):
    j = await _make_junction(session)
    await _arrive(session, j.id)
    r = await _clear(session, j.id)
    assert r.applied is True
    assert r.queue_delta == -1
    assert r.queue_count == 0


async def test_clear_without_arrival_is_recorded_but_clamped(session):
    j = await _make_junction(session)
    r = await _clear(session, j.id)
    assert r.applied is False
    assert r.queue_delta == 0
    assert r.queue_count == 0
    assert r.reason == "CLEAR_WITHOUT_ARRIVAL"


async def test_duplicate_event_is_rejected_without_side_effects(session):
    j = await _make_junction(session)
    eid = "evt-dup-1"
    first = await _arrive(session, j.id, event_id=eid)
    second = await _arrive(session, j.id, event_id=eid)
    assert first.applied is True
    assert second.applied is False
    assert second.reason == "DUPLICATE"
    rows = (await session.execute(
        select(SensorEvent).where(SensorEvent.junction_id == j.id)
    )).scalars().all()
    assert len(rows) == 1


async def test_same_event_id_on_different_junctions_is_not_duplicate(session):
    j1 = await _make_junction(session, "j1")
    j2 = await _make_junction(session, "j2")
    r1 = await _arrive(session, j1.id, event_id="shared")
    r2 = await _arrive(session, j2.id, event_id="shared")
    assert r1.applied is True
    assert r2.applied is True


async def test_unknown_junction_raises(session):
    with pytest.raises(JunctionNotFound):
        await _arrive(session, uuid.uuid4())


async def test_check_constraint_prevents_negative_count(session):
    j = await _make_junction(session)
    entry = QueueEntry(
        junction_id=j.id, direction="NORTH",
        vehicle_type="TRUCK", count=-1,
    )
    session.add(entry)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_clear_storm_never_drifts_below_zero(session):
    j = await _make_junction(session)
    await _arrive(session, j.id)
    for _ in range(5):
        await _clear(session, j.id)
    row = (await session.execute(
        select(QueueEntry).where(
            QueueEntry.junction_id == j.id,
            QueueEntry.direction == "NORTH",
            QueueEntry.vehicle_type == "TRUCK",
        )
    )).scalar_one()
    assert row.count == 0