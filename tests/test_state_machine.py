import pytest

from app.config import settings
from app.domain.enums import Direction, LogicalState, SignalState
from app.domain.state_machine import (
    SIGNALS_PER_STATE, assert_no_conflicting_green, compute_next,
    is_legal_transition, signals_for,
)


def test_no_state_has_conflicting_greens():
    for state, signals in SIGNALS_PER_STATE.items():
        try:
            assert_no_conflicting_green(signals)
        except AssertionError as e:
            pytest.fail(f"State {state.name} is unsafe: {e}")


def test_ns_green_cannot_go_directly_to_ew_green():
    assert not is_legal_transition(LogicalState.NS_GREEN, LogicalState.EW_GREEN)


def test_ew_green_cannot_go_directly_to_ns_green():
    assert not is_legal_transition(LogicalState.EW_GREEN, LogicalState.NS_GREEN)


def test_safe_sequence_ns_to_ew():
    assert is_legal_transition(LogicalState.NS_GREEN, LogicalState.NS_YELLOW)
    assert is_legal_transition(LogicalState.NS_YELLOW, LogicalState.ALL_RED)
    assert is_legal_transition(LogicalState.ALL_RED, LogicalState.EW_GREEN)


def test_ns_green_stays_green_before_interval():
    assert compute_next(LogicalState.NS_GREEN, settings.green_seconds - 0.1) is None


def test_ns_green_goes_to_yellow_at_interval():
    assert compute_next(LogicalState.NS_GREEN, settings.green_seconds) is LogicalState.NS_YELLOW


def test_yellow_goes_to_all_red():
    assert compute_next(LogicalState.NS_YELLOW, settings.yellow_seconds) is LogicalState.ALL_RED


def test_all_red_goes_to_proposed_green():
    assert compute_next(
        LogicalState.ALL_RED, settings.all_red_seconds, LogicalState.EW_GREEN,
    ) is LogicalState.EW_GREEN


def test_all_red_without_proposal_stays():
    assert compute_next(LogicalState.ALL_RED, settings.all_red_seconds + 100) is None


def test_all_red_with_illegal_proposal_stays():
    assert compute_next(
        LogicalState.ALL_RED, settings.all_red_seconds, LogicalState.UNKNOWN,
    ) is None


def test_unknown_has_no_automatic_transition():
    assert compute_next(LogicalState.UNKNOWN, 10_000) is None


def test_signals_for_returns_copy():
    sig = signals_for(LogicalState.ALL_RED)
    sig[Direction.NORTH] = SignalState.GREEN
    assert signals_for(LogicalState.ALL_RED)[Direction.NORTH] is SignalState.RED