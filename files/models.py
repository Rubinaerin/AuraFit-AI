import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Numeric, SmallInteger, Boolean, Text,
    ForeignKey, CheckConstraint, TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(10))
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    height_cm: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    current_weight_kg: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    target_weight_kg: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    fitness_level: Mapped[str] = mapped_column(String(20), nullable=False, default="beginner")
    primary_goal: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("gender IN ('male', 'female', 'other')", name="ck_users_gender"),
        CheckConstraint("fitness_level IN ('beginner', 'intermediate', 'advanced')", name="ck_users_fitness_level"),
        CheckConstraint(
            "primary_goal IN ('weight_loss', 'muscle_gain', 'endurance', 'flexibility', 'rehabilitation')",
            name="ck_users_primary_goal",
        ),
    )

    health_conditions: Mapped[list["UserHealthCondition"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class UserHealthCondition(Base):
    __tablename__ = "user_health_conditions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="moderate")
    affected_region: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "condition_type IN ('lumbar_hernia','knee_injury','shoulder_injury',"
            "'hypertension','diabetes','heart_condition','other')",
            name="ck_condition_type",
        ),
        CheckConstraint("severity IN ('mild', 'moderate', 'severe')", name="ck_condition_severity"),
    )

    user: Mapped["User"] = relationship(back_populates="health_conditions")
