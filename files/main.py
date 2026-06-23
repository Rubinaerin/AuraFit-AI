"""
Çalıştırmak için (bu dosyanın bulunduğu klasörden):
    uvicorn main:app --reload

Swagger UI: http://localhost:8000/docs
"""

from __future__ import annotations

import uuid
from ai_service import generate_workout_plan, preview_prompt, WorkoutPlanInput, HealthConditionInput, PostureMetricsInput
from pydantic import BaseModel, ConfigDict
from contextlib import asynccontextmanager
from typing import Annotated
from typing import Optional
from fastapi import UploadFile, File, Form
from cv_service import analyze_posture, analyze_multi_angle, combined_posture_score
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models import User
from schemas import RegisterRequest, RegisterResponse, UserResponse, HealthConditionResponse
from services import EmailAlreadyExistsError, register_user

settings = get_settings()
security = HTTPBearer()


# ─── Uygulama başlangıç/bitiş ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 {settings.app_name} başlatıldı.")
    yield
    print("Uygulama kapatılıyor.")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI destekli fitness uygulaması backend API'si",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8081"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Dependency: Token → Kullanıcı ───────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_TOKEN", "message": "Geçersiz veya süresi dolmuş token."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if not user_id:
            raise exc
    except JWTError:
        raise exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise exc
    return user


# ─── POST /auth/register ─────────────────────────────────────────────────────

@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı kaydı",
    tags=["auth"],
    responses={
        201: {"description": "Kayıt başarılı, JWT token döndürüldü."},
        409: {"description": "E-posta adresi zaten kayıtlı."},
        422: {"description": "Validasyon hatası."},
    },
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    try:
        return await register_user(db, payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_ALREADY_EXISTS",
                "message": f"'{exc.email}' adresi zaten kayıtlı. Giriş yapmayı deneyin.",
            },
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": "Sunucu hatası. Lütfen tekrar deneyin."},
        )


# ─── GET /users/me ───────────────────────────────────────────────────────────

@app.get(
    "/users/me",
    response_model=UserResponse,
    summary="Mevcut kullanıcı profili",
    tags=["kullanıcı"],
    responses={
        200: {"description": "Kullanıcı profili döndürüldü."},
        401: {"description": "Token geçersiz veya eksik."},
    },
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        gender=current_user.gender,
        birth_year=current_user.birth_year,
        height_cm=float(current_user.height_cm),
        current_weight_kg=float(current_user.current_weight_kg),
        target_weight_kg=float(current_user.target_weight_kg),
        fitness_level=current_user.fitness_level,
        primary_goal=current_user.primary_goal,
        health_conditions=[
            HealthConditionResponse(
                id=c.id,
                condition_type=c.condition_type,
                description=c.description,
                severity=c.severity,
                affected_region=c.affected_region,
                is_active=c.is_active,
            )
            for c in current_user.health_conditions
        ],
    )


# ─── GET /health ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["sistem"])
async def health_check():
    return {"status": "ok", "app": settings.app_name}

from fastapi import UploadFile, File, Form
from cv_service import analyze_posture, analyze_multi_angle, combined_posture_score
 
 
# ─── POST /analysis/posture/single ──────────────────────────────────────────
# Tek açıdan fotoğraf analizi
 
@app.post(
    "/analysis/posture/single",
    summary="Tek açıdan postür analizi",
    tags=["analiz"],
)
async def analyze_single_photo(
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(..., description="JPG/PNG fotoğraf"),
    angle: str = Form("front", description="front | back | left | right"),
):
    if angle not in ("front", "back", "left", "right"):
        raise HTTPException(status_code=422, detail="Geçersiz açı. front/back/left/right kullanın.")
 
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Sadece JPG, PNG veya WebP kabul edilir.")
 
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="Dosya 10 MB'dan büyük olamaz.")
 
    result = analyze_posture(image_bytes, photo_angle=angle, return_annotated=True)
 
    if not result.success:
        raise HTTPException(status_code=422, detail=result.error_message)
 
    return {
        "user_id": str(current_user.id),
        "photo_angle": result.photo_angle,
        "posture_score": result.posture_score,
        "metrics": {
            "shoulder_tilt_deg":       result.metrics.shoulder_tilt_deg,
            "hip_tilt_deg":            result.metrics.hip_tilt_deg,
            "spine_lateral_dev_deg":   result.metrics.spine_lateral_dev_deg,
            "shoulder_width_ratio":    result.metrics.shoulder_width_ratio,
            "head_forward_deg":        result.metrics.head_forward_deg,
            "torso_lean_deg":          result.metrics.torso_lean_deg,
        },
        "warnings": result.metrics.warnings,
        "detection_confidence": result.metrics.detection_confidence,
        "db_payload": result.to_db_dict(),   # photo_analyses tablosuna doğrudan kaydet
    }
 
 
# ─── POST /analysis/posture/multi ───────────────────────────────────────────
# 2–4 açıdan toplu analiz → birleşik skor
 
@app.post(
    "/analysis/posture/multi",
    summary="Çok açılı postür analizi (2-4 fotoğraf)",
    tags=["analiz"],
)
async def analyze_multi_photos(
    current_user: Annotated[User, Depends(get_current_user)],
    front: Optional[UploadFile] = File(None),
    back:  Optional[UploadFile] = File(None),
    left:  Optional[UploadFile] = File(None),
    right: Optional[UploadFile] = File(None),
):
    photos: dict = {}
    for angle, upload in [("front", front), ("back", back), ("left", left), ("right", right)]:
        if upload is not None:
            photos[angle] = await upload.read()
 
    if not photos:
        raise HTTPException(status_code=422, detail="En az bir fotoğraf yükleyin.")
 
    results = analyze_multi_angle(photos, return_annotated=False)
    overall_score = combined_posture_score(results)
 
    # Tüm uyarıları birleştir (tekrar eden uyarıları ayıkla)
    all_warnings = list({w for r in results.values() for w in r.metrics.warnings})
 
    return {
        "user_id": str(current_user.id),
        "overall_posture_score": overall_score,
        "per_angle": {
            angle: {
                "success": r.success,
                "score":   r.posture_score,
                "metrics": r.to_db_dict()["body_measurements"],
                "error":   r.error_message,
            }
            for angle, r in results.items()
        },
        "all_warnings": all_warnings,
    }

from ai_service import (
    generate_workout_plan, preview_prompt,
    WorkoutPlanInput, HealthConditionInput, PostureMetricsInput,
)
from pydantic import BaseModel


# ─── İstek Şeması ─────────────────────────────────────────────────────────────

class GeneratePlanRequest(BaseModel):
    available_days_per_week: int = 3
    available_equipment: list[str] = ["dumbbell", "body weight"]
    program_duration_weeks: int = 8
    preferred_provider: str = "auto"   # "auto" | "openai" | "anthropic"
    # Postür metrikleri opsiyonel — cv_service çıktısını buraya yapıştır
    posture_metrics: Optional[dict] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "available_days_per_week": 3,
                "available_equipment": ["dumbbell", "body weight", "resistance band"],
                "program_duration_weeks": 8,
                "preferred_provider": "auto",
                "posture_metrics": {
                    "shoulder_tilt_deg": 6.2,
                    "hip_tilt_deg": 2.1,
                    "posture_score": 74.0
                }
            }
        }
    )


# ─── POST /workout/generate ───────────────────────────────────────────────────

@app.post(
    "/workout/generate",
    summary="AI ile antrenman programı oluştur",
    tags=["antrenman"],
    responses={
        200: {"description": "Program üretildi, DB payload'ları hazır."},
        401: {"description": "Token geçersiz."},
        500: {"description": "LLM çağrısı başarısız."},
    },
)
async def generate_plan(
    request: GeneratePlanRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Kullanıcının yaşını hesapla
    current_year = __import__("datetime").date.today().year
    age = current_year - current_user.birth_year if current_user.birth_year else 30

    # Sakatlık bilgilerini dönüştür
    health_conditions = [
        HealthConditionInput(
            condition_type=c.condition_type,
            severity=c.severity,
            affected_region=c.affected_region,
            description=c.description,
        )
        for c in current_user.health_conditions
        if c.is_active
    ]

    # Postür metriklerini dönüştür (varsa)
    posture = None
    if request.posture_metrics:
        pm = request.posture_metrics
        posture = PostureMetricsInput(
            shoulder_tilt_deg=pm.get("shoulder_tilt_deg"),
            hip_tilt_deg=pm.get("hip_tilt_deg"),
            spine_lateral_dev_deg=pm.get("spine_lateral_dev_deg"),
            shoulder_width_ratio=pm.get("shoulder_width_ratio"),
            head_forward_deg=pm.get("head_forward_deg"),
            torso_lean_deg=pm.get("torso_lean_deg"),
            posture_score=pm.get("posture_score"),
        )

    plan_input = WorkoutPlanInput(
        user_id=str(current_user.id),
        full_name=current_user.full_name,
        age=age,
        gender=current_user.gender or "unspecified",
        height_cm=float(current_user.height_cm),
        current_weight_kg=float(current_user.current_weight_kg),
        target_weight_kg=float(current_user.target_weight_kg),
        fitness_level=current_user.fitness_level,
        primary_goal=current_user.primary_goal,
        health_conditions=health_conditions,
        posture_metrics=posture,
        available_days_per_week=request.available_days_per_week,
        available_equipment=request.available_equipment,
        program_duration_weeks=request.program_duration_weeks,
    )

    try:
        result = await generate_workout_plan(plan_input, request.preferred_provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "message": "Program başarıyla oluşturuldu.",
        "llm_provider": result.llm_provider,
        "generation_time_ms": result.generation_time_ms,
        "validation_warnings": result.warnings,
        # workout_plans tablosuna yazılacak:
        "db_plan_payload": result.db_plan_payload,
        # workout_days + workout_day_exercises tablosuna yazılacak:
        "db_days_payload": result.db_days_payload,
        # Ham LLM çıktısı (debug için):
        "raw_plan": result.raw_json,
    }


# ─── GET /workout/preview-prompt ─────────────────────────────────────────────
# Gerçek API çağrısı yapmadan prompt'u görüntüle (geliştirme aracı)

@app.get(
    "/workout/preview-prompt",
    summary="LLM'e gönderilecek prompt'u önizle (dev only)",
    tags=["antrenman"],
)
async def preview_plan_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
):
    current_year = __import__("datetime").date.today().year
    age = current_year - current_user.birth_year if current_user.birth_year else 30

    dummy_input = WorkoutPlanInput(
        user_id=str(current_user.id),
        full_name=current_user.full_name,
        age=age,
        gender=current_user.gender or "unspecified",
        height_cm=float(current_user.height_cm),
        current_weight_kg=float(current_user.current_weight_kg),
        target_weight_kg=float(current_user.target_weight_kg),
        fitness_level=current_user.fitness_level,
        primary_goal=current_user.primary_goal,
        health_conditions=[
            HealthConditionInput(
                condition_type=c.condition_type,
                severity=c.severity,
                affected_region=c.affected_region,
            )
            for c in current_user.health_conditions if c.is_active
        ],
    )
    prompts = preview_prompt(dummy_input)
    return {
        "system_prompt_chars": len(prompts["system_prompt"]),
        "user_prompt": prompts["user_prompt"],
    }
