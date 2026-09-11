"""
AuditLog — NOT one of Ch4's 33 documented entities, added here to actually
satisfy FR1.5 ("log all user actions with timestamps for audit trail
purposes"), which the data dictionary references but never backs with a
table. Flagged in the build plan; drop this and swap in whatever the
supervisor prefers if the report needs to match the dictionary exactly.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
