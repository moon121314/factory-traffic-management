from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.domain.enums import (
    Direction, LogicalState, VEHICLE_PRIORITY_WEIGHT, VehicleType,
)
from app.models.queue_entry import QueueEntry

_NS_DIRECTIONS = (Direction.NORTH.value, Direction.SOUTH.value)
_EW_DIRECTIONS = (Direction.EAST.value, Direction.WEST.value)


def _score(
    entries: list[QueueEntry],
    directions: tuple[str, ...],
    now: datetime,
) -> tuple[float, float]:
    weighted = 0
    max_wait = 0.0
    for e in entries:
        if e.direction not in directions:
            continue
        if e.count <= 0:
            continue
        try:
            weight = VEHICLE_PRIORITY_WEIGHT[VehicleType(e.vehicle_type)]
        except (ValueError, KeyError):
            weight = 1
        weighted += e.count * weight
        if e.oldest_arrival_at is not None:
            wait_s = (now - e.oldest_arrival_at).total_seconds()
            if wait_s > max_wait:
                max_wait = wait_s
    score = weighted + max_wait * settings.wait_time_boost
    return float(score), float(max_wait)


def choose_next_green(
    queue_entries: list[QueueEntry],
    now: datetime,
) -> tuple[LogicalState, str]:
    ns_score, ns_wait = _score(queue_entries, _NS_DIRECTIONS, now)
    ew_score, ew_wait = _score(queue_entries, _EW_DIRECTIONS, now)

    starve = settings.starvation_seconds
    if ns_wait >= starve and ns_wait > ew_wait:
        return LogicalState.NS_GREEN, f"STARVATION_NS({ns_wait:.0f}s)"
    if ew_wait >= starve and ew_wait > ns_wait:
        return LogicalState.EW_GREEN, f"STARVATION_EW({ew_wait:.0f}s)"

    if ns_score > ew_score:
        return LogicalState.NS_GREEN, f"SCORE_NS({ns_score:.1f})"
    if ew_score > ns_score:
        return LogicalState.EW_GREEN, f"SCORE_EW({ew_score:.1f})"

    return LogicalState.NS_GREEN, "TIE_DEFAULT_NS"