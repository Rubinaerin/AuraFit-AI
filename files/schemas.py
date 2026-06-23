from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict


# ─── Enum'lar ────────────────────────────────────────────────────────────────

class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class FitnessLevelEnum(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class PrimaryGoalEnum(str, Enum):
    weight_loss = "weight_loss"
    muscle_gain = "muscle_gain"
    endurance = "endurance"
    flexibility = "flexibility"
    rehabilitation = "rehabilitation"


class ConditionTypeEnum(str, Enum):
    lumbar_hernia = "lumbar_hernia"
    knee_injury = "knee_injury"
    shoulder_injury = "shoulder_injury"
    hypertension = "hypertension"
    diabetes = "diabetes"
    heart_condition = "heart_condition"
    other = "other"


class SeverityEnum(str, Enum):
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


# ─── İstek Şemaları ──────────────────────────────────────────────────────────

class HealthConditionSchema(BaseModel):
    condition_type: ConditionTypeEnum
    description: str | None = Field(default=None, max_length=500)
    severity: SeverityEnum = SeverityEnum.moderate
    affected_region: str | None = Field(default=None, max_length=50)

    model_config = ConfigDict(use_enum_values=True)


class PhysicalDataSchema(BaseModel):
    height_cm: Annotated[float, Field(gt=100, lt=250, examples=[175.0])]
    current_weight_kg: Annotated[float, Field(gt=30, lt=300, examples=[80.0])]
    target_weight_kg: Annotated[float, Field(gt=30, lt=300, examples=[70.0])]
    gender: GenderEnum
    birth_year: Annotated[int, Field(ge=1930, le=date.today().year - 10, examples=[1995])]
    fitness_level: FitnessLevelEnum = FitnessLevelEnum.beginner
    primary_goal: PrimaryGoalEnum

    @model_validator(mode="after")
    def validate_weight_goal(self) -> PhysicalDataSchema:
        diff = abs(self.current_weight_kg - self.target_weight_kg)
        if diff > 100:
            raise ValueError(
                "Mevcut kilo ile hedef kilo arasındaki fark 100 kg'dan fazla olamaz."
            )
        return self

    model_config = ConfigDict(use_enum_values=True)


class UserCreateSchema(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    full_name: Annotated[str, Field(min_length=2, max_length=100)]

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Şifre en az bir büyük harf içermelidir.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Şifre en az bir küçük harf içermelidir.")
        if not re.search(r"\d", v):
            raise ValueError("Şifre en az bir rakam içermelidir.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        return v.strip()

    model_config = ConfigDict(str_strip_whitespace=True)


class RegisterRequest(BaseModel):
    user: UserCreateSchema
    physical_data: PhysicalDataSchema
    health_conditions: list[HealthConditionSchema] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user": {
                    "email": "ahmet@example.com",
                    "password": "Guclu1Sifre",
                    "full_name": "Ahmet Yilmaz",
                },
                "physical_data": {
                    "height_cm": 178.0,
                    "current_weight_kg": 85.0,
                    "target_weight_kg": 75.0,
                    "gender": "male",
                    "birth_year": 1995,
                    "fitness_level": "beginner",
                    "primary_goal": "weight_loss",
                },
                "health_conditions": [
                    {
                        "condition_type": "lumbar_hernia",
                        "description": "L4-L5 fitigi, egzersizde dikkatli olunmali",
                        "severity": "moderate",
                        "affected_region": "lower_back",
                    }
                ],
            }
        }
    )


# ─── Yanıt Şemaları ──────────────────────────────────────────────────────────

class HealthConditionResponse(BaseModel):
    id: UUID
    condition_type: str
    description: str | None
    severity: str
    affected_region: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    gender: str | None
    birth_year: int | None
    height_cm: float
    current_weight_kg: float
    target_weight_kg: float
    fitness_level: str
    primary_goal: str
    health_conditions: list[HealthConditionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class RegisterResponse(BaseModel):
    message: str
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    has_health_conditions: bool
    rehabilitation_warning: bool
