from datetime import timedelta

from app.config import settings
from app.domain.enums import LogicalState
from app.models.queue_entry import QueueEntry
from app.services import policy


def _entry(junction_id, direction, vehicle_type, count, oldest_arrival_at=None):
    return QueueEntry(
        junction_id=junction_id, direction=direction,
        vehicle_type=vehicle_type, count=count,
        oldest_arrival_at=oldest_arrival_at,
    )


def test_higher_weight_wins_on_equal_count(clock):
    entries = [
        _entry(None, "EAST", "EMERGENCY", count=1),
        _entry(None, "NORTH", "EMPLOYEE_VEHICLE", count=1),
    ]
    green, _ = policy.choose_next_green(entries, clock.now())
    assert green is LogicalState.EW_GREEN


def test_more_count_wins_when_weights_equal(clock):
    entries = [
        _entry(None, "NORTH", "TRUCK", count=3),
        _entry(None, "EAST", "TRUCK", count=1),
    ]
    green, _ = policy.choose_next_green(entries, clock.now())
    assert green is LogicalState.NS_GREEN


def test_starvation_overrides_score(clock):
    entries = [
        _entry(None, "NORTH", "TRUCK", count=10),
        _entry(None, "EAST", "EMPLOYEE_VEHICLE", count=1,
               oldest_arrival_at=clock.now() - timedelta(
                   seconds=settings.starvation_seconds + 5)),
    ]
    green, reason = policy.choose_next_green(entries, clock.now())
    assert green is LogicalState.EW_GREEN
    assert "STARVATION" in reason


def test_empty_queues_default_to_ns(clock):
    green, reason = policy.choose_next_green([], clock.now())
    assert green is LogicalState.NS_GREEN
    assert reason == "TIE_DEFAULT_NS"


def test_wait_time_boost_can_decide(clock):
    entries = [
        _entry(None, "NORTH", "TRUCK", count=1),
        _entry(None, "EAST", "TRUCK", count=1,
               oldest_arrival_at=clock.now() - timedelta(seconds=20)),
    ]
    green, reason = policy.choose_next_green(entries, clock.now())
    assert green is LogicalState.EW_GREEN
    assert "SCORE" in reason