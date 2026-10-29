from enum import Enum


class Direction(str, Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"


class Phase(str, Enum):
    NS = "NS"
    EW = "EW"


PHASE_DIRECTIONS: dict[Phase, tuple[Direction, ...]] = {
    Phase.NS: (Direction.NORTH, Direction.SOUTH),
    Phase.EW: (Direction.EAST, Direction.WEST),
}


def phase_for(direction: Direction) -> Phase:
    if direction in (Direction.NORTH, Direction.SOUTH):
        return Phase.NS
    return Phase.EW


def conflicting_phase(phase: Phase) -> Phase:
    return Phase.EW if phase is Phase.NS else Phase.NS


class SignalState(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    UNKNOWN = "UNKNOWN"


class JunctionMode(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    EMERGENCY = "EMERGENCY"
    RECOVERING = "RECOVERING"


class VehicleType(str, Enum):
    EMERGENCY = "EMERGENCY"
    TRUCK = "TRUCK"
    FORKLIFT = "FORKLIFT"
    EMPLOYEE_VEHICLE = "EMPLOYEE_VEHICLE"


VEHICLE_PRIORITY_WEIGHT: dict[VehicleType, int] = {
    VehicleType.EMERGENCY: 100,
    VehicleType.TRUCK: 10,
    VehicleType.FORKLIFT: 4,
    VehicleType.EMPLOYEE_VEHICLE: 1,
}


class SensorEventType(str, Enum):
    VEHICLE_ARRIVED = "VEHICLE_ARRIVED"
    VEHICLE_CLEARED = "VEHICLE_CLEARED"


class LogicalState(str, Enum):
    NS_GREEN = "NS_GREEN"
    NS_YELLOW = "NS_YELLOW"
    EW_GREEN = "EW_GREEN"
    EW_YELLOW = "EW_YELLOW"
    ALL_RED = "ALL_RED"
    EMERGENCY_NS_GREEN = "EMERGENCY_NS_GREEN"
    EMERGENCY_EW_GREEN = "EMERGENCY_EW_GREEN"
    MANUAL_NS_GREEN = "MANUAL_NS_GREEN"
    MANUAL_EW_GREEN = "MANUAL_EW_GREEN"
    UNKNOWN = "UNKNOWN"


class CommandType(str, Enum):
    MANUAL_GREEN_REQUEST = "MANUAL_GREEN_REQUEST"
    RETURN_TO_AUTOMATIC = "RETURN_TO_AUTOMATIC"
    EMERGENCY_REQUEST = "EMERGENCY_REQUEST"
    MANUAL_EXPIRED = "MANUAL_EXPIRED"
    EMERGENCY_TIMEOUT = "EMERGENCY_TIMEOUT"
    EMERGENCY_CLEARED = "EMERGENCY_CLEARED"


class CommandStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CLEARED = "CLEARED"
    NO_OP = "NO_OP"


class ControllerCommandStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKED = "ACKED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"