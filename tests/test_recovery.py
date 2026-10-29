from sqlalchemy import select

from app.controller.interface import ControllerError
from app.controller.rest_simulator import SimulatorControllerClient
from app.domain.enums import (
    ControllerCommandStatus, Direction, JunctionMode, LogicalState, SignalState,
)
from app.models.transition import Transition
from app.repositories import (
    controller_command_repo as cmd_repo,
    junction_repo,
    signal_state_repo,
)
from app.services import recovery_service


class UnreachableController:
    async def send_command(self, *args, **kwargs):
        raise ControllerError("unreachable")
    async def query_state(self):
        raise ControllerError("unreachable")


class UnsafeController:
    async def send_command(self, *args, **kwargs):
        raise ControllerError("unreachable")
    async def query_state(self):
        return {
            Direction.NORTH: SignalState.GREEN,
            Direction.SOUTH: SignalState.GREEN,
            Direction.EAST:  SignalState.GREEN,
            Direction.WEST:  SignalState.RED,
        }


class AllRedController:
    async def send_command(self, *args, **kwargs):
        raise ControllerError("unused")
    async def query_state(self):
        return {d: SignalState.RED for d in Direction}


async def _make_junction(session, clock, name, state):
    j = await junction_repo.create(session, name)
    j.logical_state = state.value
    j.state_started_at = clock.now()
    j.mode = JunctionMode.AUTO.value
    await session.commit()
    await signal_state_repo.ensure_all_directions(session, j.id)
    await session.commit()
    return j


async def _transitions(session, jid):
    stmt = (
        select(Transition)
        .where(Transition.junction_id == jid)
        .order_by(Transition.created_at, Transition.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def test_recovery_no_junctions(session, clock):
    await recovery_service.recover_all(session, clock, SimulatorControllerClient())


async def test_recovery_marks_all_unknown_before_resolving(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.NS_GREEN)
    await recovery_service.recover_all(session, clock, UnreachableController())
    await session.refresh(j)
    assert j.logical_state == LogicalState.UNKNOWN.value
    assert j.mode == JunctionMode.RECOVERING.value


async def test_recovery_fails_inflight_commands(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.NS_GREEN)
    cmd = await cmd_repo.create(
        session, junction_id=j.id, command_id="inflight-1",
        target_json='{"NORTH":"GREEN"}',
    )
    await cmd_repo.mark_sent(session, cmd.id, clock.now())
    await session.commit()
    await recovery_service.recover_all(session, clock, SimulatorControllerClient())
    updated = await cmd_repo.find_by_command_id(session, "inflight-1")
    assert updated.status == ControllerCommandStatus.FAILED.value


async def test_recovery_unreachable_stays_recovering(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.NS_GREEN)
    await recovery_service.recover_all(session, clock, UnreachableController())
    await session.refresh(j)
    assert j.mode == JunctionMode.RECOVERING.value


async def test_recovery_resolves_to_all_red(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.NS_GREEN)
    await recovery_service.recover_all(session, clock, AllRedController())
    await session.refresh(j)
    assert j.logical_state == LogicalState.ALL_RED.value
    assert j.mode == JunctionMode.AUTO.value


async def test_recovery_unsafe_state_stays_recovering(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.ALL_RED)
    await recovery_service.recover_all(session, clock, UnsafeController())
    await session.refresh(j)
    assert j.mode == JunctionMode.RECOVERING.value


async def test_recovery_writes_audit_transitions(session, clock):
    j = await _make_junction(session, clock, "j1", LogicalState.NS_GREEN)
    await recovery_service.recover_all(session, clock, AllRedController())
    transitions = await _transitions(session, j.id)
    pairs = [(t.from_state, t.to_state, t.reason) for t in transitions]
    assert (LogicalState.NS_GREEN.value, LogicalState.UNKNOWN.value,
            "RECOVERY_STARTED") in pairs
    assert (LogicalState.UNKNOWN.value, LogicalState.ALL_RED.value,
            "RECOVERY_RESOLVED") in pairs