from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.clock import Clock, SystemClock
from app.domain.enums import (
    CommandStatus, CommandType, JunctionMode, LogicalState, Phase,
)
from app.domain.state_machine import is_legal_transition
from app.models.junction import Junction
from app.repositories import command_repo, junction_repo


class JunctionNotFound(Exception):
    pass


class CommandRejected(Exception):
    pass


@dataclass(frozen=True)
class CommandOutcome:
    accepted: bool
    status: str
    detail: str


async def _reject(session, junction, command_type, phase, detail):
    await command_repo.record(
        session, junction_id=junction.id,
        command_type=command_type,
        phase=phase.value if phase else None,
        status=CommandStatus.REJECTED.value,
        detail=detail,
    )
    await session.commit()


async def request_manual_green(
    session: AsyncSession,
    junction_id,
    phase: Phase,
    clock: Clock | None = None,
) -> CommandOutcome:
    clock = clock or SystemClock()
    now = clock.now()

    junction = await junction_repo.get_for_update(session, junction_id)
    if junction is None:
        raise JunctionNotFound(str(junction_id))

    if junction.mode == JunctionMode.RECOVERING.value:
        await _reject(session, junction, CommandType.MANUAL_GREEN_REQUEST.value,
                      phase, "junction in recovery")
        raise CommandRejected("junction is in recovery mode")

    if junction.mode == JunctionMode.EMERGENCY.value:
        await _reject(session, junction, CommandType.MANUAL_GREEN_REQUEST.value,
                      phase, "emergency in progress")
        raise CommandRejected("emergency in progress; manual request rejected")

    if junction.mode == JunctionMode.MANUAL.value:
        if junction.desired_phase != phase.value:
            await _reject(
                session, junction, CommandType.MANUAL_GREEN_REQUEST.value,
                phase, f"manual already active for {junction.desired_phase}",
            )
            raise CommandRejected(
                f"manual already active for {junction.desired_phase}; "
                f"RETURN_TO_AUTOMATIC first"
            )
        junction.mode_expires_at = now + timedelta(
            seconds=settings.manual_override_seconds
        )
        await command_repo.record(
            session, junction_id=junction.id,
            command_type=CommandType.MANUAL_GREEN_REQUEST.value,
            phase=phase.value, status=CommandStatus.ACCEPTED.value,
            detail="EXTENDED",
        )
        await session.commit()
        return CommandOutcome(True, CommandStatus.ACCEPTED.value,
                              "manual override extended")

    junction.mode = JunctionMode.MANUAL.value
    junction.desired_phase = phase.value
    junction.mode_expires_at = now + timedelta(
        seconds=settings.manual_override_seconds
    )

    detail = "WAIT_FOR_ALL_RED"
    if phase is Phase.NS and junction.logical_state == LogicalState.NS_GREEN.value:
        if is_legal_transition(LogicalState.NS_GREEN, LogicalState.MANUAL_NS_GREEN):
            junction.logical_state = LogicalState.MANUAL_NS_GREEN.value
            junction.state_started_at = now
            detail = "UPGRADED_IN_PLACE"
    elif phase is Phase.EW and junction.logical_state == LogicalState.EW_GREEN.value:
        if is_legal_transition(LogicalState.EW_GREEN, LogicalState.MANUAL_EW_GREEN):
            junction.logical_state = LogicalState.MANUAL_EW_GREEN.value
            junction.state_started_at = now
            detail = "UPGRADED_IN_PLACE"

    await command_repo.record(
        session, junction_id=junction.id,
        command_type=CommandType.MANUAL_GREEN_REQUEST.value,
        phase=phase.value, status=CommandStatus.ACCEPTED.value,
        detail=detail,
    )
    await session.commit()
    return CommandOutcome(True, CommandStatus.ACCEPTED.value, detail)


async def request_emergency(
    session: AsyncSession,
    junction_id,
    phase: Phase,
    clock: Clock | None = None,
) -> CommandOutcome:
    clock = clock or SystemClock()
    now = clock.now()

    junction = await junction_repo.get_for_update(session, junction_id)
    if junction is None:
        raise JunctionNotFound(str(junction_id))

    if junction.mode == JunctionMode.RECOVERING.value:
        await _reject(session, junction, CommandType.EMERGENCY_REQUEST.value,
                      phase, "junction in recovery")
        raise CommandRejected("junction is in recovery mode")

    if junction.mode == JunctionMode.EMERGENCY.value:
        if junction.desired_phase != phase.value:
            await _reject(
                session, junction, CommandType.EMERGENCY_REQUEST.value, phase,
                f"conflicting emergency in progress ({junction.desired_phase})",
            )
            raise CommandRejected(
                f"conflicting emergency already in progress "
                f"({junction.desired_phase}); wait for it to clear or time out"
            )
        junction.mode_expires_at = now + timedelta(
            seconds=settings.emergency_max_seconds
        )
        await command_repo.record(
            session, junction_id=junction.id,
            command_type=CommandType.EMERGENCY_REQUEST.value,
            phase=phase.value, status=CommandStatus.ACCEPTED.value,
            detail="EXTENDED",
        )
        await session.commit()
        return CommandOutcome(True, CommandStatus.ACCEPTED.value,
                              "emergency timeout extended")

    previous_mode = junction.mode
    junction.mode = JunctionMode.EMERGENCY.value
    junction.desired_phase = phase.value
    junction.mode_expires_at = now + timedelta(
        seconds=settings.emergency_max_seconds
    )

    current = junction.logical_state
    detail = "WAIT_FOR_ALL_RED"

    if phase is Phase.NS:
        if current in (LogicalState.NS_GREEN.value, LogicalState.MANUAL_NS_GREEN.value):
            junction.logical_state = LogicalState.EMERGENCY_NS_GREEN.value
            junction.state_started_at = now
            detail = "UPGRADED_IN_PLACE"
        elif current in (LogicalState.EW_GREEN.value, LogicalState.MANUAL_EW_GREEN.value):
            junction.state_started_at = now - timedelta(seconds=10_000)
            detail = "PREEMPT_OPPOSITE_GREEN"
    else:
        if current in (LogicalState.EW_GREEN.value, LogicalState.MANUAL_EW_GREEN.value):
            junction.logical_state = LogicalState.EMERGENCY_EW_GREEN.value
            junction.state_started_at = now
            detail = "UPGRADED_IN_PLACE"
        elif current in (LogicalState.NS_GREEN.value, LogicalState.MANUAL_NS_GREEN.value):
            junction.state_started_at = now - timedelta(seconds=10_000)
            detail = "PREEMPT_OPPOSITE_GREEN"

    await command_repo.record(
        session, junction_id=junction.id,
        command_type=CommandType.EMERGENCY_REQUEST.value,
        phase=phase.value, status=CommandStatus.ACCEPTED.value,
        detail=f"{detail} (was {previous_mode})",
    )
    await session.commit()
    return CommandOutcome(True, CommandStatus.ACCEPTED.value, detail)


async def return_to_automatic(
    session: AsyncSession,
    junction_id,
    clock: Clock | None = None,
) -> CommandOutcome:
    clock = clock or SystemClock()
    now = clock.now()

    junction = await junction_repo.get_for_update(session, junction_id)
    if junction is None:
        raise JunctionNotFound(str(junction_id))

    if junction.mode == JunctionMode.EMERGENCY.value:
        await _reject(session, junction, CommandType.RETURN_TO_AUTOMATIC.value,
                      None, "emergency must clear via sensor or timeout")
        raise CommandRejected("emergency in progress; cannot cancel manually")

    if junction.mode == JunctionMode.AUTO.value:
        await command_repo.record(
            session, junction_id=junction.id,
            command_type=CommandType.RETURN_TO_AUTOMATIC.value,
            phase=None, status=CommandStatus.NO_OP.value,
            detail="already automatic",
        )
        await session.commit()
        return CommandOutcome(True, CommandStatus.NO_OP.value, "already automatic")

    junction.mode = JunctionMode.AUTO.value
    junction.desired_phase = None
    junction.mode_expires_at = None

    if junction.logical_state in (
        LogicalState.MANUAL_NS_GREEN.value,
        LogicalState.MANUAL_EW_GREEN.value,
    ):
        junction.state_started_at = now - timedelta(seconds=10_000)

    await command_repo.record(
        session, junction_id=junction.id,
        command_type=CommandType.RETURN_TO_AUTOMATIC.value,
        phase=None, status=CommandStatus.ACCEPTED.value,
        detail="returned to automatic",
    )
    await session.commit()
    return CommandOutcome(True, CommandStatus.ACCEPTED.value,
                          "returned to automatic")


async def on_emergency_cleared(
    session: AsyncSession,
    junction: Junction,
    phase: Phase,
    clock: Clock | None = None,
) -> None:
    if junction.mode != JunctionMode.EMERGENCY.value:
        return
    if junction.desired_phase != phase.value:
        return

    clock = clock or SystemClock()
    now = clock.now()

    junction.mode = JunctionMode.AUTO.value
    junction.desired_phase = None
    junction.mode_expires_at = None

    if junction.logical_state in (
        LogicalState.EMERGENCY_NS_GREEN.value,
        LogicalState.EMERGENCY_EW_GREEN.value,
    ):
        junction.state_started_at = now - timedelta(seconds=10_000)

    await command_repo.record(
        session, junction_id=junction.id,
        command_type=CommandType.EMERGENCY_CLEARED.value,
        phase=phase.value, status=CommandStatus.CLEARED.value,
        detail="cleared by sensor event",
    )