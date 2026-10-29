import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import Direction, SensorEventType, VehicleType


class SensorEventIn(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=255)
    junction_id: uuid.UUID
    event_type: SensorEventType
    direction: Direction
    vehicle_type: VehicleType
    occurred_at: Optional[datetime] = None


class SensorEventOut(BaseModel):
    applied: bool
    queue_delta: int
    queue_count: int
    reason: Optional[str] = None