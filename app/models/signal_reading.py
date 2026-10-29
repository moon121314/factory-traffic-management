import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.domain.enums import SignalState


class SignalReading(Base):
    __tablename__ = "signal_readings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    junction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("junctions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    confirmed: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SignalState.UNKNOWN.value,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "junction_id", "direction",
            name="uq_signal_reading_junction_direction",
        ),
    )