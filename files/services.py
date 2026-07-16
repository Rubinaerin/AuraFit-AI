from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import User, UserHealthCondition
from schemas import (
    RegisterRequest, RegisterResponse,
    UserResponse, HealthConditionResponse,
)

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


async def register_user(db: AsyncSession, data: RegisterRequest) -> RegisterResponse:
    import traceback # Hatanın tüm satır detayını terminale dökmek için ekledik
    
    try:
        # 1. Email benzersizlik kontrolü (Artık try bloğunun içinde, hata verirse yakalanacak)
        existing = await db.execute(select(User).where(User.email == data.user.email.lower()))
        if existing.scalar_one_or_none():
            raise EmailAlreadyExistsError(data.user.email)

        # 2. Kullanıcı oluştur
        user = User(
            email=data.user.email.lower(),
            password_hash=hash_password(data.user.password),
            full_name=data.user.full_name,
            gender=data.physical_data.gender,
            birth_year=data.physical_data.birth_year,
            height_cm=data.physical_data.height_cm,
            current_weight_kg=data.physical_data.current_weight_kg,
            target_weight_kg=data.physical_data.target_weight_kg,
            fitness_level=data.physical_data.fitness_level,
            primary_goal=data.physical_data.primary_goal,
        )
        db.add(user)
        await db.flush()  # Commit etmeden önce ID'yi üret

        # 3. Sakatlık kayıtları (Sadece geçerli olanları ekle)
        valid_conditions = {
            'lumbar_hernia', 'knee_injury', 'shoulder_injury',
            'hypertension', 'diabetes', 'heart_condition', 'other'
        }

        for cond in data.health_conditions:
            if cond.condition_type in valid_conditions:
                db.add(UserHealthCondition(
                    user_id=user.id,
                    condition_type=cond.condition_type,
                    description=cond.description or "No description provided.",
                    severity=cond.severity,
                    affected_region=cond.affected_region,
                ))

        # 4. Atomik commit
        await db.commit()
        await db.refresh(user)

    except Exception as db_err:
        await db.rollback()
        # ─── Terminale Hata Çıktısını Zorla Yazdırıyoruz ───────────────────
        print("\n❌ DATABASE REGISTRATION ERROR DETECTED:")
        traceback.print_exc() # Hatanın hangi satırda ve neden gerçekleştiğini tam detaylı basar
        print("──────────────────────────────────────────\n")
        raise db_err

    has_conditions = len(user.health_conditions) > 0
    rehab_warning = has_conditions and data.physical_data.primary_goal != "rehabilitation"

    return RegisterResponse(
        message="Kayit basarili! Antrenman programiniz hazirlaniyor.",
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            gender=user.gender,
            birth_year=user.birth_year,
            height_cm=float(user.height_cm),
            current_weight_kg=float(user.current_weight_kg),
            target_weight_kg=float(user.target_weight_kg),
            fitness_level=user.fitness_level,
            primary_goal=user.primary_goal,
            health_conditions=[
                HealthConditionResponse(
                    id=c.id,
                    condition_type=c.condition_type,
                    description=c.description,
                    severity=c.severity,
                    affected_region=c.affected_region,
                    is_active=c.is_active,
                )
                for c in user.health_conditions
            ],
        ),
        access_token=create_access_token(user.id),
        token_type="bearer",
        has_health_conditions=has_conditions,
        rehabilitation_warning=rehab_warning,
    )


class EmailAlreadyExistsError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Bu e-posta adresi zaten kayitli: {email}")

from models import User, UserHealthCondition # En altta modellerin import edildiğinden emin olalım

async def update_user_profile(db, user: User, data: UpdateProfileRequest) -> User:
    if data.physical_data:
        pd = data.physical_data
        user.height_cm = pd.get("height_cm", user.height_cm)
        user.current_weight_kg = pd.get("current_weight_kg", user.current_weight_kg)
        user.target_weight_kg = pd.get("target_weight_kg", user.target_weight_kg)
        user.gender = pd.get("gender", user.gender)
        user.fitness_level = pd.get("fitness_level", user.fitness_level)
        user.primary_goal = pd.get("primary_goal", user.primary_goal)

    if data.health_conditions is not None:
        # Mevcut sakatlıkları temizle
        for existing in list(user.health_conditions):
            await db.delete(existing)
        await db.flush()

        # Yeni gelen sakatlık listesini ekle
        for cond in data.health_conditions:
            db.add(UserHealthCondition(
                user_id=user.id,
                condition_type=cond.get("condition_type"),
                description=cond.get("description"),
                severity=cond.get("severity"),
                affected_region=cond.get("affected_region"),
            ))

    await db.commit()
    await db.refresh(user)
    return user