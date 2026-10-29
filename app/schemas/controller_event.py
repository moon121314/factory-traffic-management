from pydantic import BaseModel

from app.domain.enums import Direction, SignalState


class ControllerEventIn(BaseModel):
    command_id: str
    accepted: bool
    signals: dict[Direction, SignalState]
    reason: str | None = None


class ControllerEventOut(BaseModel):
    ok: bool