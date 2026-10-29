import logging

import httpx

from app.controller.interface import Ack, ControllerClient, ControllerError
from app.domain.enums import Direction, SignalState

logger = logging.getLogger(__name__)


class SimulatorControllerClient:
    def __init__(self, base_state: dict[Direction, SignalState] | None = None):
        self._state: dict[Direction, SignalState] = (
            dict(base_state) if base_state else {d: SignalState.RED for d in Direction}
        )

    async def send_command(self, command_id, target_signals):
        self._state = dict(target_signals)
        return Ack(
            command_id=command_id,
            accepted=True,
            confirmed_signals=dict(self._state),
        )

    async def query_state(self):
        return dict(self._state)


class RestControllerClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def send_command(self, command_id, target_signals):
        payload = {
            "command_id": command_id,
            "signals": {d.value: s.value for d, s in target_signals.items()},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(f"{self._base_url}/command", json=payload)
        except httpx.HTTPError as e:
            raise ControllerError(f"controller unreachable: {e}") from e

        if r.status_code == 202:
            return None
        if r.status_code >= 400:
            raise ControllerError(f"controller error {r.status_code}: {r.text}")

        try:
            body = r.json()
            return Ack(
                command_id=body.get("command_id", command_id),
                accepted=bool(body.get("accepted", False)),
                confirmed_signals={
                    Direction(k): SignalState(v) for k, v in body["signals"].items()
                },
                reason=body.get("reason"),
            )
        except (KeyError, ValueError) as e:
            raise ControllerError(f"malformed response: {e}") from e

    async def query_state(self):
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(f"{self._base_url}/state")
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        try:
            body = r.json()
            return {Direction(k): SignalState(v) for k, v in body["signals"].items()}
        except (KeyError, ValueError):
            return None
