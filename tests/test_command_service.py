from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.domain.enums import (
    Direction, JunctionMode, LogicalState, Phase,
    SensorEventType, VehicleType,
)
from app.models.command import Command
from app.services import command_service, event_service, scheduler_service


async def _make(session, clock, name="j1", state=LogicalState.ALL_RED):
    from app.repositories import junction_repo
    j = await junction_repo.create(session, name)
    j.logical_state = state.value
    j.state_started_at = clock.now()
    j.mode = JunctionMode.AUTO.value
    await session.commit()
    return j


async def _tick(session, clock):
    return await scheduler_service.tick(session, clock)


async def _commands(session, jid):
    stmt = select(Command).where(Command.junction_id == jid).order_by(Command.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def test_manual_during_auto_same_phase_upgrades(session, clock):
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    await command_service.request_manual_green(session, j.id, Phase.NS, clock=clock)
    await session.refresh(j)
    assert j.mode == JunctionMode.MANUAL.value
    assert j.logical_state == LogicalState.MANUAL_NS_GREEN.value


async def test_manual_during_opposite_green_waits(session, clock):
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    await command_service.request_manual_green(session, j.id, Phase.EW, clock=clock)
    await session.refresh(j)
    assert j.logical_state == LogicalState.NS_GREEN.value
    clock.advance(settings.green_seconds); await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.NS_YELLOW.value
    clock.advance(settings.yellow_seconds); await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.ALL_RED.value
    clock.advance(settings.all_red_seconds); await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.MANUAL_EW_GREEN.value


async def test_emergency_upgrades_same_phase(session, clock):
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    await command_service.request_emergency(session, j.id, Phase.NS, clock=clock)
    await session.refresh(j)
    assert j.mode == JunctionMode.EMERGENCY.value
    assert j.logical_state == LogicalState.EMERGENCY_NS_GREEN.value


async def test_emergency_preempts_opposite_green(session, clock):
    j = await _make(session, clock, state=LogicalState.EW_GREEN)
    await command_service.request_emergency(session, j.id, Phase.NS, clock=clock)
    await session.refresh(j)
    assert j.logical_state == LogicalState.EW_GREEN.value
    await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.EW_YELLOW.value
    clock.advance(settings.yellow_seconds); await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.ALL_RED.value
    clock.advance(settings.all_red_seconds); await _tick(session, clock)
    await session.refresh(j); assert j.logical_state == LogicalState.EMERGENCY_NS_GREEN.value


async def test_conflicting_emergency_rejected(session, clock):
    j = await _make(session, clock, state=LogicalState.EMERGENCY_NS_GREEN)
    j.mode = JunctionMode.EMERGENCY.value
    j.desired_phase = Phase.NS.value
    j.mode_expires_at = clock.now() + timedelta(seconds=60)
    await session.commit()
    with pytest.raises(command_service.CommandRejected):
        await command_service.request_emergency(session, j.id, Phase.EW, clock=clock)


async def test_manual_during_emergency_rejected(session, clock):
    j = await _make(session, clock, state=LogicalState.EMERGENCY_NS_GREEN)
    j.mode = JunctionMode.EMERGENCY.value
    j.desired_phase = Phase.NS.value
    j.mode_expires_at = clock.now() + timedelta(seconds=60)
    await session.commit()
    with pytest.raises(command_service.CommandRejected):
        await command_service.request_manual_green(session, j.id, Phase.NS, clock=clock)


async def test_emergency_clears_on_vehicle_cleared(session, clock):
    j = await _make(session, clock, state=LogicalState.EMERGENCY_NS_GREEN)
    j.mode = JunctionMode.EMERGENCY.value
    j.desired_phase = Phase.NS.value
    j.mode_expires_at = clock.now() + timedelta(seconds=60)
    await session.commit()

    await event_service.process_sensor_event(
        session, junction_id=j.id, event_id="arr",
        event_type=SensorEventType.VEHICLE_ARRIVED,
        direction=Direction.NORTH.value,
        vehicle_type=VehicleType.EMERGENCY.value, occurred_at=None,
    )
    await event_service.process_sensor_event(
        session, junction_id=j.id, event_id="clr",
        event_type=SensorEventType.VEHICLE_CLEARED,
        direction=Direction.NORTH.value,
        vehicle_type=VehicleType.EMERGENCY.value, occurred_at=None,
    )

    await session.refresh(j)
    assert j.mode == JunctionMode.AUTO.value


async def test_emergency_times_out(session, clock):
    j = await _make(session, clock, state=LogicalState.EMERGENCY_NS_GREEN)
    j.mode = JunctionMode.EMERGENCY.value
    j.desired_phase = Phase.NS.value
    j.mode_expires_at = clock.now() + timedelta(seconds=settings.emergency_max_seconds)
    await session.commit()
    clock.advance(settings.emergency_max_seconds)
    await _tick(session, clock)
    await session.refresh(j)
    assert j.mode == JunctionMode.AUTO.value