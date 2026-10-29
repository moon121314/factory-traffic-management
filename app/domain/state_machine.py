from app.config import settings
from app.domain.enums import Direction, LogicalState, SignalState


SIGNALS_PER_STATE: dict[LogicalState, dict[Direction, SignalState]] = {
    LogicalState.NS_GREEN: {
        Direction.NORTH: SignalState.GREEN,
        Direction.SOUTH: SignalState.GREEN,
        Direction.EAST:  SignalState.RED,
        Direction.WEST:  SignalState.RED,
    },
    LogicalState.NS_YELLOW: {
        Direction.NORTH: SignalState.YELLOW,
        Direction.SOUTH: SignalState.YELLOW,
        Direction.EAST:  SignalState.RED,
        Direction.WEST:  SignalState.RED,
    },
    LogicalState.EW_GREEN: {
        Direction.NORTH: SignalState.RED,
        Direction.SOUTH: SignalState.RED,
        Direction.EAST:  SignalState.GREEN,
        Direction.WEST:  SignalState.GREEN,
    },
    LogicalState.EW_YELLOW: {
        Direction.NORTH: SignalState.RED,
        Direction.SOUTH: SignalState.RED,
        Direction.EAST:  SignalState.YELLOW,
        Direction.WEST:  SignalState.YELLOW,
    },
    LogicalState.ALL_RED: {
        Direction.NORTH: SignalState.RED,
        Direction.SOUTH: SignalState.RED,
        Direction.EAST:  SignalState.RED,
        Direction.WEST:  SignalState.RED,
    },
    LogicalState.EMERGENCY_NS_GREEN: {
        Direction.NORTH: SignalState.GREEN,
        Direction.SOUTH: SignalState.GREEN,
        Direction.EAST:  SignalState.RED,
        Direction.WEST:  SignalState.RED,
    },
    LogicalState.EMERGENCY_EW_GREEN: {
        Direction.NORTH: SignalState.RED,
        Direction.SOUTH: SignalState.RED,
        Direction.EAST:  SignalState.GREEN,
        Direction.WEST:  SignalState.GREEN,
    },
    LogicalState.MANUAL_NS_GREEN: {
        Direction.NORTH: SignalState.GREEN,
        Direction.SOUTH: SignalState.GREEN,
        Direction.EAST:  SignalState.RED,
        Direction.WEST:  SignalState.RED,
    },
    LogicalState.MANUAL_EW_GREEN: {
        Direction.NORTH: SignalState.RED,
        Direction.SOUTH: SignalState.RED,
        Direction.EAST:  SignalState.GREEN,
        Direction.WEST:  SignalState.GREEN,
    },
    LogicalState.UNKNOWN: {
        Direction.NORTH: SignalState.UNKNOWN,
        Direction.SOUTH: SignalState.UNKNOWN,
        Direction.EAST:  SignalState.UNKNOWN,
        Direction.WEST:  SignalState.UNKNOWN,
    },
}


ALLOWED_TRANSITIONS: dict[LogicalState, frozenset[LogicalState]] = {
    LogicalState.NS_GREEN: frozenset({
        LogicalState.NS_YELLOW,
        LogicalState.MANUAL_NS_GREEN,
        LogicalState.EMERGENCY_NS_GREEN,
    }),
    LogicalState.EW_GREEN: frozenset({
        LogicalState.EW_YELLOW,
        LogicalState.MANUAL_EW_GREEN,
        LogicalState.EMERGENCY_EW_GREEN,
    }),
    LogicalState.NS_YELLOW: frozenset({LogicalState.ALL_RED}),
    LogicalState.EW_YELLOW: frozenset({LogicalState.ALL_RED}),
    LogicalState.ALL_RED: frozenset({
        LogicalState.NS_GREEN,
        LogicalState.EW_GREEN,
        LogicalState.EMERGENCY_NS_GREEN,
        LogicalState.EMERGENCY_EW_GREEN,
        LogicalState.MANUAL_NS_GREEN,
        LogicalState.MANUAL_EW_GREEN,
    }),
    LogicalState.MANUAL_NS_GREEN: frozenset({
        LogicalState.NS_YELLOW,
        LogicalState.EMERGENCY_NS_GREEN,
    }),
    LogicalState.MANUAL_EW_GREEN: frozenset({
        LogicalState.EW_YELLOW,
        LogicalState.EMERGENCY_EW_GREEN,
    }),
    LogicalState.EMERGENCY_NS_GREEN: frozenset({LogicalState.NS_YELLOW}),
    LogicalState.EMERGENCY_EW_GREEN: frozenset({LogicalState.EW_YELLOW}),
    LogicalState.UNKNOWN: frozenset({LogicalState.ALL_RED}),
}


def signals_for(state: LogicalState) -> dict[Direction, SignalState]:
    return dict(SIGNALS_PER_STATE[state])


def is_legal_transition(from_state: LogicalState, to_state: LogicalState) -> bool:
    return to_state in ALLOWED_TRANSITIONS[from_state]


_CANONICAL_STATE_FOR_SIGNALS: dict[
    tuple[SignalState, SignalState, SignalState, SignalState],
    LogicalState,
] = {
    (SignalState.GREEN,  SignalState.GREEN,  SignalState.RED,    SignalState.RED):
        LogicalState.NS_GREEN,
    (SignalState.YELLOW, SignalState.YELLOW, SignalState.RED,    SignalState.RED):
        LogicalState.NS_YELLOW,
    (SignalState.RED,    SignalState.RED,    SignalState.GREEN,  SignalState.GREEN):
        LogicalState.EW_GREEN,
    (SignalState.RED,    SignalState.RED,    SignalState.YELLOW, SignalState.YELLOW):
        LogicalState.EW_YELLOW,
    (SignalState.RED,    SignalState.RED,    SignalState.RED,    SignalState.RED):
        LogicalState.ALL_RED,
}


def canonical_state_for(
    signals: dict[Direction, SignalState],
) -> LogicalState | None:
    key = (
        signals[Direction.NORTH],
        signals[Direction.SOUTH],
        signals[Direction.EAST],
        signals[Direction.WEST],
    )
    return _CANONICAL_STATE_FOR_SIGNALS.get(key)


def _green_interval_for(state: LogicalState) -> float:
    if state in (LogicalState.MANUAL_NS_GREEN, LogicalState.MANUAL_EW_GREEN):
        return settings.manual_override_seconds
    if state in (LogicalState.EMERGENCY_NS_GREEN, LogicalState.EMERGENCY_EW_GREEN):
        return settings.emergency_max_seconds
    return settings.green_seconds


def compute_next(
    current: LogicalState,
    elapsed_seconds: float,
    proposed_green: LogicalState | None = None,
) -> LogicalState | None:

    if current in (
        LogicalState.NS_GREEN, LogicalState.EW_GREEN,
        LogicalState.EMERGENCY_NS_GREEN, LogicalState.EMERGENCY_EW_GREEN,
        LogicalState.MANUAL_NS_GREEN, LogicalState.MANUAL_EW_GREEN,
    ):
        if elapsed_seconds < _green_interval_for(current):
            return None
        if current in (
            LogicalState.NS_GREEN,
            LogicalState.EMERGENCY_NS_GREEN,
            LogicalState.MANUAL_NS_GREEN,
        ):
            return LogicalState.NS_YELLOW
        return LogicalState.EW_YELLOW

    if current in (LogicalState.NS_YELLOW, LogicalState.EW_YELLOW):
        if elapsed_seconds < settings.yellow_seconds:
            return None
        return LogicalState.ALL_RED

    if current is LogicalState.ALL_RED:
        if elapsed_seconds < settings.all_red_seconds:
            return None
        if proposed_green is None:
            return None
        if not is_legal_transition(current, proposed_green):
            return None
        return proposed_green

    return None


def assert_no_conflicting_green(signals: dict[Direction, SignalState]) -> None:
    
    if any(state is SignalState.UNKNOWN for state in signals.values()):
        return

    ns_active = (
        signals[Direction.NORTH] is not SignalState.RED
        or signals[Direction.SOUTH] is not SignalState.RED
    )
    ew_active = (
        signals[Direction.EAST] is not SignalState.RED
        or signals[Direction.WEST] is not SignalState.RED
    )
    assert not (ns_active and ew_active), (
        f"Conflicting green. NS={ns_active}, EW={ew_active}. Signals: {signals}"
    )