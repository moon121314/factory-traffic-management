from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.domain.enums import JunctionMode, LogicalState
from app.domain.state_machine import is_legal_transition
from app.models.transition import Transition
from app.repositories import junction_repo, queue_repo
from app.services import scheduler_service


async def _make_junction(session, clock, name="j1", state=LogicalState.ALL_RED):
    j = await junction_repo.create(session, name)
    j.logical_state = state.value
    j.state_started_at = clock.now()
    j.mode = JunctionMode.AUTO.value
    await session.commit()
    return j


async def _add_queue(session, clock, junction_id, direction, vehicle_type,
                     count=1, age_seconds=0.0):
    entry = await queue_repo.get_or_create(
        session, junction_id, direction, vehicle_type
    )
    if entry.count == 0:
        entry.oldest_arrival_at = clock.now() - timedelta(seconds=age_seconds)
    entry.count += count
    await session.commit()
    return entry


async def _transitions(session, junction_id):
    stmt = (
        select(Transition)
        .where(Transition.junction_id == junction_id)
        .order_by(Transition.created_at, Transition.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _tick(session, clock):
    return await scheduler_service.tick(session, clock)


async def test_all_red_goes_to_ns_green_with_ns_queue(session, clock):
    j = await _make_junction(session, clock)
    await _add_queue(session, clock, j.id, "NORTH", "TRUCK", count=3)
    clock.advance(settings.all_red_seconds + 1)
    assert await _tick(session, clock) == 1
    await session.refresh(j)
    assert j.logical_state == LogicalState.NS_GREEN.value


async def test_no_transition_before_interval(session, clock):
    j = await _make_junction(session, clock, state=LogicalState.NS_GREEN)
    clock.advance(settings.green_seconds - 0.1)
    assert await _tick(session, clock) == 0


async def test_manual_mode_advances_through_safe_sequence(session, clock):
    """Phase Six: MANUAL junctions ARE advanced by the scheduler, but
    through the manual path — not skipped entirely."""
    from datetime import timedelta
    j = await _make_junction(session, clock, state=LogicalState.MANUAL_NS_GREEN)
    j.mode = JunctionMode.MANUAL.value
    j.desired_phase = "NS"
    j.mode_expires_at = clock.now() + timedelta(seconds=600)
    await session.commit()

    # Advance past the manual green interval.
    clock.advance(600 + 1)
    n = await _tick(session, clock)
    assert n == 1
    await session.refresh(j)
    assert j.logical_state == LogicalState.NS_YELLOW.value


async def test_unknown_state_is_skipped(session, clock):
    j = await _make_junction(session, clock, state=LogicalState.UNKNOWN)
    clock.advance(10_000)
    assert await _tick(session, clock) == 0


async def test_ns_green_goes_to_yellow_at_interval(session, clock):
    j = await _make_junction(session, clock, state=LogicalState.NS_GREEN)
    clock.advance(settings.green_seconds)
    assert await _tick(session, clock) == 1
    await session.refresh(j)
    assert j.logical_state == LogicalState.NS_YELLOW.value


async def test_no_illegal_transitions_over_many_cycles(session, clock):
    j = await _make_junction(session, clock)
    await _add_queue(session, clock, j.id, "NORTH", "TRUCK", count=2)
    await _add_queue(session, clock, j.id, "EAST", "TRUCK", count=2)
    for _ in range(500):
        clock.advance(1.0)
        await _tick(session, clock)
    rows = await _transitions(session, j.id)
    for r in rows:
        assert is_legal_transition(
            LogicalState(r.from_state), LogicalState(r.to_state)
        )