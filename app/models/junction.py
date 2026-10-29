import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.domain.enums import JunctionMode, LogicalState


class Junction(Base):
    __tablename__ = "junctions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    logical_state: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=LogicalState.UNKNOWN.value,
        server_default=LogicalState.UNKNOWN.value,
    )
    state_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False,
        default=JunctionMode.AUTO.value,
        server_default=JunctionMode.AUTO.value,
    )
    desired_phase: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    mode_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )