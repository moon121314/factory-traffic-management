import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String,
    UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    junction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("junctions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(50), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oldest_arrival_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "junction_id", "direction", "vehicle_type",
            name="uq_queue_entry_junction_dir_veh",
        ),
        CheckConstraint("count >= 0", name="ck_queue_entry_count_non_negative"),
    )