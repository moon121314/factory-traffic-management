from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import Phase


class CommandIn(BaseModel):
    command_type: str = Field(
        ...,
        pattern="^(MANUAL_GREEN_REQUEST|RETURN_TO_AUTOMATIC|EMERGENCY_REQUEST)$",
    )
    phase: Optional[Phase] = None


class CommandOut(BaseModel):
    accepted: bool
    status: str
    detail: str