from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.controller.interface import Ack, ControllerClient, ControllerError
from app.domain.clock import Clock
from app.domain.enums import ControllerCommandStatus, LogicalState
from app.domain.state_machine import signals_for
from app.models.junction import Junction
from app.repositories import (
    controller_command_repo as cmd_repo,
    junction_repo,
    signal_state_repo,
)

logger = logging.getLogger(__name__)


async def dispatch_pending(
    session: AsyncSession,
    clock: Clock,
    client: ControllerClient,
) -> int:
    junctions = await junction_repo.list_all_for_update(session)
    sent = 0
    for junction in junctions:
        sent += await _dispatch_for_junction(session, junction, clock, client)
    await session.commit()
    return sent


async def _dispatch_for_junction(
    session: AsyncSession,
    junction: Junction,
    clock: Clock,
    client: ControllerClient,
) -> int:
    if junction.logical_state == LogicalState.UNKNOWN.value:
        return 0

    inflight = await cmd_repo.find_inflight(session, junction.id)
    if inflight is not None:
        return 0

    failures = await cmd_repo.count_recent_failures(
        session, junction.id, limit=settings.command_max_retries + 1
    )
    if failures >= settings.command_max_retries:
        logger.warning(
            "Junction %s: %d consecutive failures; not dispatching",
            junction.id, failures,
        )
        return 0

    desired = signals_for(LogicalState(junction.logical_state))
    await signal_state_repo.ensure_all_directions(session, junction.id)
    confirmed = await signal_state_repo.get_dict(session, junction.id)

    if dict(desired) == dict(confirmed):
        return 0

    command_id = str(uuid.uuid4())
    target_json = json.dumps({d.value: s.value for d, s in desired.items()})
    cmd = await cmd_repo.create(
        session, junction_id=junction.id,
        command_id=command_id, target_json=target_json,
    )
    await session.flush()

    try:
        ack = await client.send_command(command_id, desired)
    except ControllerError as e:
        logger.warning("Junction %s: send failed: %s", junction.id, e)
        await cmd_repo.mark_failed(session, cmd.id, str(e))
        return 1

    if ack is None:
        await cmd_repo.mark_sent(session, cmd.id, clock.now())
        logger.info("Junction %s: command %s sent (async ACK pending)",
                    junction.id, command_id)
    else:
        await cmd_repo.mark_acked(session, cmd.id, clock.now())
        await _apply_ack_signals(session, junction.id, ack)
        logger.info("Junction %s: command %s ACKed synchronously",
                    junction.id, command_id)
    return 1


async def _apply_ack_signals(session, junction_id, ack):
    for direction, state in ack.confirmed_signals.items():
        await signal_state_repo.set_confirmed(session, junction_id, direction, state)


async def on_ack(session: AsyncSession, ack: Ack, clock: Clock) -> None:
    cmd = await cmd_repo.find_by_command_id(session, ack.command_id)
    if cmd is None:
        logger.warning("ACK for unknown command %s; ignoring", ack.command_id)
        return

    if cmd.status in (
        ControllerCommandStatus.ACKED.value,
        ControllerCommandStatus.REJECTED.value,
        ControllerCommandStatus.FAILED.value,
    ):
        logger.info(
            "ACK for already-finalized command %s (status=%s); ignoring",
            ack.command_id, cmd.status,
        )
        return

    if ack.accepted:
        await cmd_repo.mark_acked(session, cmd.id, clock.now())
        await _apply_ack_signals(session, cmd.junction_id, ack)
    else:
        await cmd_repo.mark_rejected(
            session, cmd.id, ack.reason or "rejected by controller",
        )
    await session.commit()


async def poll_timeouts(session: AsyncSession, clock: Clock) -> int:
    cutoff = clock.now() - timedelta(seconds=settings.command_timeout_seconds)
    overdue = await cmd_repo.find_overdue(session, cutoff)
    for cmd in overdue:
        await cmd_repo.mark_timeout(session, cmd.id)
        logger.warning("Command %s for junction %s timed out",
                       cmd.command_id, cmd.junction_id)
    await session.commit()
    return len(overdue)