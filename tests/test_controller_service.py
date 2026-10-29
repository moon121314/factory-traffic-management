import json

from app.controller.interface import Ack, ControllerError
from app.controller.rest_simulator import SimulatorControllerClient
from app.domain.enums import Direction, LogicalState, SignalState
from app.domain.state_machine import signals_for
from app.repositories import (
    controller_command_repo as cmd_repo,
    junction_repo,
    signal_state_repo,
)
from app.services import controller_service, scheduler_service


async def _make(session, clock, state=LogicalState.ALL_RED, name="j1"):
    j = await junction_repo.create(session, name)
    j.logical_state = state.value
    j.state_started_at = clock.now()
    await session.commit()
    await signal_state_repo.ensure_all_directions(session, j.id)
    await session.commit()
    return j


async def test_sync_ack_updates_confirmed(session, clock):
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    client = SimulatorControllerClient()
    sent = await controller_service.dispatch_pending(session, clock, client)
    assert sent == 1
    confirmed = await signal_state_repo.get_dict(session, j.id)
    assert confirmed[Direction.NORTH] is SignalState.GREEN


async def test_duplicate_ack_is_ignored(session, clock):
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    command_id = "cmd-dup-1"
    target = json.dumps({d.value: s.value for d, s in
                         signals_for(LogicalState.NS_GREEN).items()})
    cmd = await cmd_repo.create(session, junction_id=j.id,
                                command_id=command_id, target_json=target)
    await cmd_repo.mark_sent(session, cmd.id, clock.now())
    await session.commit()

    ack = Ack(command_id=command_id, accepted=True,
              confirmed_signals=signals_for(LogicalState.NS_GREEN))
    await controller_service.on_ack(session, ack, clock)
    await controller_service.on_ack(session, ack, clock)
    updated = await cmd_repo.find_by_command_id(session, command_id)
    assert updated.status == "ACKED"


async def test_timeout_marks_sent(session, clock):
    from app.config import settings
    j = await _make(session, clock, state=LogicalState.NS_GREEN)
    command_id = "cmd-timeout-1"
    target = json.dumps({d.value: s.value for d, s in
                         signals_for(LogicalState.NS_GREEN).items()})
    cmd = await cmd_repo.create(session, junction_id=j.id,
                                command_id=command_id, target_json=target)
    await cmd_repo.mark_sent(session, cmd.id, clock.now())
    await session.commit()
    clock.advance(settings.command_timeout_seconds + 1)
    n = await controller_service.poll_timeouts(session, clock)
    assert n == 1
    updated = await cmd_repo.find_by_command_id(session, command_id)
    assert updated.status == "TIMEOUT"


async def test_repeated_failures_stop_dispatch(session, clock):
    from app.config import settings
    j = await _make(session, clock, state=LogicalState.NS_GREEN)

    class FailingClient:
        async def send_command(self, command_id, target_signals):
            raise ControllerError("simulated failure")
        async def query_state(self):
            return None

    for _ in range(settings.command_max_retries):
        await controller_service.dispatch_pending(session, clock, FailingClient())
        clock.advance(1)
    sent = await controller_service.dispatch_pending(session, clock, FailingClient())
    assert sent == 0