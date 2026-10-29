from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import Clock
from app.domain.enums import JunctionMode, LogicalState, Phase
from app.domain.state_machine import compute_next, is_legal_transition
from app.models.junction import Junction
from app.models.transition import Transition
from app.repositories import command_repo, junction_repo, queue_repo
from app.services import policy

logger = logging.getLogger(__name__)


async def tick(session: AsyncSession, clock: Clock) -> int:
    junctions = await junction_repo.list_all_for_update(session)
    total = 0
    for junction in junctions:
        total += await _process_junction(session, junction, clock)
    await session.commit()
    return total


async def _process_junction(
    session: AsyncSession,
    junction: Junction,
    clock: Clock,
) -> int:

    if junction.mode == JunctionMode.RECOVERING.value:
        return 0
    if junction.logical_state == LogicalState.UNKNOWN.value:
        return 0

    now = clock.now()

    if junction.mode in (JunctionMode.MANUAL.value, JunctionMode.EMERGENCY.value):
        if junction.mode_expires_at is not None and now >= junction.mode_expires_at:
            expired_mode = junction.mode
            junction.mode = JunctionMode.AUTO.value
            junction.desired_phase = None
            junction.mode_expires_at = None

            await command_repo.record(
                session, junction_id=junction.id,
                command_type=(
                    "MANUAL_EXPIRED" if expired_mode == JunctionMode.MANUAL.value
                    else "EMERGENCY_TIMEOUT"
                ),
                phase=None, status="EXPIRED",
                detail=f"{expired_mode.lower()} override expired",
            )

            if junction.logical_state in (
                LogicalState.MANUAL_NS_GREEN.value,
                LogicalState.MANUAL_EW_GREEN.value,
                LogicalState.EMERGENCY_NS_GREEN.value,
                LogicalState.EMERGENCY_EW_GREEN.value,
            ):
                junction.state_started_at = now - timedelta(seconds=10_000)

    current = LogicalState(junction.logical_state)
    if junction.state_started_at is None:
        logger.warning("Junction %s in %s with no state_started_at", junction.id, current)
        return 0

    elapsed = (now - junction.state_started_at).total_seconds()

    proposed: LogicalState | None = None
    proposed_reason = ""
    if current is LogicalState.ALL_RED:
        if junction.mode == JunctionMode.MANUAL.value:
            phase = junction.desired_phase
            proposed = (
                LogicalState.MANUAL_NS_GREEN if phase == Phase.NS.value
                else LogicalState.MANUAL_EW_GREEN
            )
            proposed_reason = f"MANUAL_{phase}"
        elif junction.mode == JunctionMode.EMERGENCY.value:
            phase = junction.desired_phase
            proposed = (
                LogicalState.EMERGENCY_NS_GREEN if phase == Phase.NS.value
                else LogicalState.EMERGENCY_EW_GREEN
            )
            proposed_reason = f"EMERGENCY_{phase}"
        else:
            entries = await queue_repo.list_for_junction(session, junction.id)
            proposed, proposed_reason = policy.choose_next_green(entries, now)

    next_state = compute_next(current, elapsed, proposed)
    if next_state is None:
        return 0

    if not is_legal_transition(current, next_state):
        logger.error(
            "Refusing illegal transition on junction %s: %s → %s",
            junction.id, current, next_state,
        )
        return 0

    reason = _reason_for(current, next_state, proposed_reason)
    session.add(Transition(
        junction_id=junction.id,
        from_state=current.value,
        to_state=next_state.value,
        reason=reason,
    ))
    junction.logical_state = next_state.value
    junction.state_started_at = now
    logger.info(
        "Junction %s: %s → %s (%s)",
        junction.id, current.value, next_state.value, reason,
    )
    return 1


def _reason_for(
    from_state: LogicalState,
    to_state: LogicalState,
    policy_reason: str,
) -> str:
    if from_state in (
        LogicalState.NS_GREEN, LogicalState.EW_GREEN,
        LogicalState.EMERGENCY_NS_GREEN, LogicalState.EMERGENCY_EW_GREEN,
        LogicalState.MANUAL_NS_GREEN, LogicalState.MANUAL_EW_GREEN,
    ):
        return "GREEN_EXPIRED"
    if from_state in (LogicalState.NS_YELLOW, LogicalState.EW_YELLOW):
        return "YELLOW_EXPIRED"
    if from_state is LogicalState.ALL_RED:
        return f"POLICY_{policy_reason}" if policy_reason else "POLICY_NONE"
    return f"{from_state.value}->{to_state.value}"