"""All junction endpoints: create, list, get, status, history."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.domain.enums import LogicalState
from app.domain.state_machine import signals_for
from app.models.command import Command
from app.models.controller_command import ControllerCommand
from app.models.transition import Transition
from app.repositories import junction_repo, queue_repo, signal_state_repo
from app.schemas.junction import (
    CommandSummary, HistoryEvent, JunctionCreate, JunctionOut,
    JunctionStatusOut, QueueSummary, SignalStateOut,
)

router = APIRouter(prefix="/api/junctions", tags=["junctions"])


@router.post("", response_model=JunctionOut, status_code=201)
async def create_junction(
    payload: JunctionCreate,
    session: AsyncSession = Depends(get_session),
) -> JunctionOut:
    try:
        junction = await junction_repo.create(session, payload.name)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f"Junction {payload.name!r} already exists")
    return JunctionOut.model_validate(junction)


@router.get("", response_model=list[JunctionOut])
async def list_junctions(
    session: AsyncSession = Depends(get_session),
) -> list[JunctionOut]:
    rows = await junction_repo.list_all(session)
    return [JunctionOut.model_validate(j) for j in rows]


@router.get("/{junction_id}", response_model=JunctionOut)
async def get_junction(
    junction_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JunctionOut:
    junction = await junction_repo.get(session, junction_id)
    if junction is None:
        raise HTTPException(404, "junction not found")
    return JunctionOut.model_validate(junction)


@router.get("/{junction_id}/status", response_model=JunctionStatusOut)
async def get_status(
    junction_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JunctionStatusOut:
    junction = await junction_repo.get(session, junction_id)
    if junction is None:
        raise HTTPException(404, "junction not found")

    try:
        current = LogicalState(junction.logical_state)
    except ValueError:
        current = LogicalState.UNKNOWN
    desired = signals_for(current) if current is not LogicalState.UNKNOWN else {
        d: __import__("app.domain.enums", fromlist=["SignalState"]).SignalState.UNKNOWN
        for d in __import__("app.domain.enums", fromlist=["Direction"]).Direction
    }

    from app.domain.enums import Direction
    await signal_state_repo.ensure_all_directions(session, junction.id)
    confirmed = await signal_state_repo.get_dict(session, junction.id)

    signal_rows = [
        SignalStateOut(
            direction=d,
            desired=desired[d],
            confirmed=confirmed[d],
        )
        for d in Direction
    ]

    entries = await queue_repo.list_for_junction(session, junction.id)
    queues = [
        QueueSummary(direction=__import__("app.domain.enums", fromlist=["Direction"]).Direction(e.direction),
                     vehicle_type=e.vehicle_type, count=e.count)
        for e in entries if e.count > 0
    ]

    stmt = select(ControllerCommand).where(
        ControllerCommand.junction_id == junction.id,
        ControllerCommand.status.in_(["PENDING", "SENT"]),
    ).order_by(ControllerCommand.created_at)
    pending = [
        CommandSummary(command_id=c.command_id, status=c.status, created_at=c.created_at)
        for c in (await session.execute(stmt)).scalars().all()
    ]

    return JunctionStatusOut(
        id=junction.id,
        name=junction.name,
        logical_state=junction.logical_state,
        mode=junction.mode,
        desired_phase=junction.desired_phase,
        mode_expires_at=junction.mode_expires_at,
        state_started_at=junction.state_started_at,
        signals=signal_rows,
        queues=queues,
        pending_commands=pending,
    )


@router.get("/{junction_id}/history", response_model=list[HistoryEvent])
async def get_history(
    junction_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[HistoryEvent]:
    junction = await junction_repo.get(session, junction_id)
    if junction is None:
        raise HTTPException(404, "junction not found")

    events: list[HistoryEvent] = []

    t_stmt = select(Transition).where(
        Transition.junction_id == junction_id
    ).order_by(Transition.created_at)
    for t in (await session.execute(t_stmt)).scalars().all():
        events.append(HistoryEvent(
            kind="transition",
            at=t.created_at,
            payload={
                "from": t.from_state,
                "to": t.to_state,
                "reason": t.reason,
            },
        ))

    c_stmt = select(Command).where(
        Command.junction_id == junction_id
    ).order_by(Command.created_at)
    for c in (await session.execute(c_stmt)).scalars().all():
        events.append(HistoryEvent(
            kind="command",
            at=c.created_at,
            payload={
                "command_type": c.command_type,
                "phase": c.phase,
                "status": c.status,
                "detail": c.detail,
            },
        ))

    cc_stmt = select(ControllerCommand).where(
        ControllerCommand.junction_id == junction_id
    ).order_by(ControllerCommand.created_at)
    for cc in (await session.execute(cc_stmt)).scalars().all():
        events.append(HistoryEvent(
            kind="controller_command",
            at=cc.created_at,
            payload={
                "command_id": cc.command_id,
                "status": cc.status,
                "sent_at": cc.sent_at.isoformat() if cc.sent_at else None,
                "acked_at": cc.acked_at.isoformat() if cc.acked_at else None,
            },
        ))

    events.sort(key=lambda e: e.at)
    return events