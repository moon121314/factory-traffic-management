import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import Direction, SignalState


class JunctionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class JunctionOut(BaseModel):
    id: uuid.UUID
    name: str
    model_config = {"from_attributes": True}


class QueueSummary(BaseModel):
    direction: Direction
    vehicle_type: str
    count: int


class SignalStateOut(BaseModel):
    direction: Direction
    desired: SignalState
    confirmed: SignalState


class CommandSummary(BaseModel):
    command_id: str
    status: str
    created_at: datetime


class JunctionStatusOut(BaseModel):
    id: uuid.UUID
    name: str
    logical_state: str
    mode: str
    desired_phase: Optional[str] = None
    mode_expires_at: Optional[datetime] = None
    state_started_at: Optional[datetime] = None
    signals: list[SignalStateOut]
    queues: list[QueueSummary]
    pending_commands: list[CommandSummary]


class HistoryEvent(BaseModel):
    kind: str  # "transition" | "command" | "controller_command"
    at: datetime
    payload: dict