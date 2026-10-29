from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controller.interface import ControllerClient, ControllerError
from app.domain.clock import Clock
from app.domain.enums import (
    ControllerCommandStatus, Direction, JunctionMode, LogicalState, SignalState,
)
from app.domain.state_machine import canonical_state_for
from app.models.junction import Junction
from app.models.transition import Transition
from app.repositories import (
    controller_command_repo as cmd_repo,
    signal_state_repo,
)

logger = logging.getLogger(__name__)


async def recover_all(
    session: AsyncSession,
    clock: Clock,
    client: ControllerClient,
) -> None:
    junctions = await _load_all_junctions(session)
    if not junctions:
        logger.info("recovery: no junctions")
        return

    logger.info("recovery: pass 1 — marking %d junctions UNKNOWN", len(junctions))
    for j in junctions:
        await _mark_unknown(session, j, clock)
    await session.commit()

    logger.info("recovery: pass 2 — resolving %d junctions", len(junctions))
    resolved, unreachable, unsafe = 0, 0, 0
    for j in junctions:
        try:
            outcome = await _try_resolve(session, j, clock, client)
        except Exception:
            logger.exception("recovery: unexpected error for junction %s", j.id)
            await session.rollback()
            continue
        if outcome == "resolved":
            resolved += 1
        elif outcome == "unreachable":
            unreachable += 1
        else:
            unsafe += 1
    await session.commit()

    logger.info(
        "recovery complete: %d resolved, %d unreachable, %d unsafe",
        resolved, unreachable, unsafe,
    )


async def _load_all_junctions(session: AsyncSession) -> list[Junction]:
    stmt = select(Junction)
    return list((await session.execute(stmt)).scalars().all())


async def _mark_unknown(session: AsyncSession, junction: Junction, clock: Clock) -> None:
    old_state = junction.logical_state

    session.add(Transition(
        junction_id=junction.id,
        from_state=old_state,
        to_state=LogicalState.UNKNOWN.value,
        reason="RECOVERY_STARTED",
    ))

    junction.logical_state = LogicalState.UNKNOWN.value
    junction.mode = JunctionMode.RECOVERING.value
    junction.state_started_at = None
    junction.desired_phase = None
    junction.mode_expires_at = None

    await signal_state_repo.ensure_all_directions(session, junction.id)
    for direction in Direction:
        await signal_state_repo.set_confirmed(
            session, junction.id, direction, SignalState.UNKNOWN
        )

    pending = await _find_inflight_commands(session, junction.id)
    for cmd in pending:
        await cmd_repo.mark_failed(session, cmd.id, "restart recovery")


async def _try_resolve(
    session: AsyncSession,
    junction: Junction,
    clock: Clock,
    client: ControllerClient,
) -> str:
    try:
        confirmed = await client.query_state()
    except ControllerError as e:
        logger.warning("recovery: unreachable for %s: %s", junction.id, e)
        return "unreachable"

    if confirmed is None:
        logger.warning("recovery: no state for junction %s", junction.id)
        return "unreachable"

    matched = canonical_state_for(confirmed)
    if matched is None:
        logger.critical(
            "recovery: unsafe state for junction %s: %s",
            junction.id, confirmed,
        )
        return "unsafe"

    session.add(Transition(
        junction_id=junction.id,
        from_state=LogicalState.UNKNOWN.value,
        to_state=matched.value,
        reason="RECOVERY_RESOLVED",
    ))
    junction.logical_state = matched.value
    junction.state_started_at = clock.now()
    junction.mode = JunctionMode.AUTO.value
    junction.desired_phase = None
    junction.mode_expires_at = None

    for direction, state in confirmed.items():
        await signal_state_repo.set_confirmed(session, junction.id, direction, state)

    logger.info("recovery: junction %s resolved to %s", junction.id, matched.value)
    return "resolved"


async def _find_inflight_commands(session: AsyncSession, junction_id):
    stmt = select(cmd_repo.ControllerCommand).where(
        cmd_repo.ControllerCommand.junction_id == junction_id,
        cmd_repo.ControllerCommand.status.in_([
            ControllerCommandStatus.PENDING.value,
            ControllerCommandStatus.SENT.value,
        ]),
    )
    return list((await session.execute(stmt)).scalars().all())