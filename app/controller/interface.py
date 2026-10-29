from dataclasses import dataclass
from typing import Protocol

from app.domain.enums import Direction, SignalState


@dataclass(frozen=True)
class Ack:
    command_id: str
    accepted: bool
    confirmed_signals: dict[Direction, SignalState]
    reason: str | None = None


class ControllerError(Exception):
    pass


class ControllerClient(Protocol):
    async def send_command(
        self,
        command_id: str,
        target_signals: dict[Direction, SignalState],
    ) -> Ack | None: ...

    async def query_state(self) -> dict[Direction, SignalState] | None: ...