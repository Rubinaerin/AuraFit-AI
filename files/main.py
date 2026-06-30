"""
Çalıştırmak için (bu dosyanın bulunduğu klasörden):
    uvicorn main:app --reload

Swagger UI: http://localhost:8000/docs
"""

from __future__ import annotations

import uuid
from ai_service import generate_workout_plan, preview_prompt, WorkoutPlanInput, HealthConditionInput, PostureMetricsInput
from pydantic import BaseModel, ConfigDict, Field, EmailStr
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
from schemas import RegisterRequest, RegisterResponse, UserResponse, HealthConditionResponse, UpdateProfileRequest
from services import EmailAlreadyExistsError, register_user, verify_password, create_access_token, update_user_profile
from chat_service import chat_with_coach, ChatInput, HealthConditionCtx, ActivePlanCtx
from progress_service import compare_posture, CompareInput, BaselineMetrics

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
    description="AI-powered posture analysis and customized workout engine Backend API",
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
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post(
    "/auth/login",
    response_model=RegisterResponse,   # reuses the same response shape as /auth/register
    summary="Log in with email and password",
    tags=["auth"],
    responses={
        200: {"description": "Login successful, JWT token returned."},
        401: {"description": "Invalid email or password."},
    },
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # Same error for "no such user" and "wrong password" — avoids leaking
    # which emails are registered (standard security practice).
    invalid_creds = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."},
    )

    if not user or not verify_password(payload.password, user.password_hash):
        raise invalid_creds

    has_conditions = len(user.health_conditions) > 0
    rehab_warning = has_conditions and user.primary_goal != "rehabilitation"

    return RegisterResponse(
        message="Login successful.",
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
                    id=c.id, condition_type=c.condition_type, description=c.description,
                    severity=c.severity, affected_region=c.affected_region, is_active=c.is_active,
                )
                for c in user.health_conditions
            ],
        ),
        access_token=create_access_token(user.id),
        token_type="bearer",
        has_health_conditions=has_conditions,
        rehabilitation_warning=rehab_warning,
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

@app.patch(
    "/users/me",
    response_model=UserResponse,
    summary="Update physical data and/or health conditions",
    tags=["kullanıcı"],
)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    updated_user = await update_user_profile(db, current_user, payload)

    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        full_name=updated_user.full_name,
        gender=updated_user.gender,
        birth_year=updated_user.birth_year,
        height_cm=float(updated_user.height_cm),
        current_weight_kg=float(updated_user.current_weight_kg),
        target_weight_kg=float(updated_user.target_weight_kg),
        fitness_level=updated_user.fitness_level,
        primary_goal=updated_user.primary_goal,
        health_conditions=[
            HealthConditionResponse(
                id=c.id, condition_type=c.condition_type, description=c.description,
                severity=c.severity, affected_region=c.affected_region, is_active=c.is_active,
            )
            for c in updated_user.health_conditions
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
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(
        default=None,
        description="Mevcut oturumu sürdürmek için doldurun. Boş bırakırsanız yeni oturum açılır."
    )
    # Aktif antrenman planı (opsiyonel — doldurulursa chatbot plana göre yanıt verir)
    plan_name: Optional[str] = None
    sessions_per_week: Optional[int] = None
    primary_goal: Optional[str] = None
    current_week: Optional[int] = None
    current_week_exercises: list[str] = Field(default_factory=list)
    preferred_provider: str = "auto"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Bel fıtığım ağrıdı, deadlift'e alternatif ne önerirsin?",
                "session_id": None,
                "plan_name": "8 Haftalık Kilo Verme Programı",
                "sessions_per_week": 3,
                "primary_goal": "weight_loss",
                "current_week": 2,
                "current_week_exercises": ["Plank", "Bird-Dog", "Lat Pulldown"],
                "preferred_provider": "auto",
            }
        }
    )


@app.post(
    "/chat/message",
    summary="AI Antrenör ile mesajlaş",
    tags=["chatbot"],
    responses={
        200: {"description": "Antrenör yanıtı döndürüldü."},
        401: {"description": "Token geçersiz."},
        500: {"description": "LLM çağrısı başarısız."},
    },
)
async def chat_message(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Hafızalı chatbot endpoint'i.

    Hafıza mekanizması:
    - İlk mesajda session_id boş gelir → yeni UUID üretilir.
    - Sonraki mesajlarda aynı session_id gönderilir.
    - Her turda DB'den o oturumun son 20 mesajı çekilip LLM'e gönderilir.
    - Böylece 'bel fıtığım ağrıdı' gibi önceki bağlam hatırlanır.
    """
    from sqlalchemy import select as sa_select

    # ── Geçmiş mesajları DB'den çek ──────────────────────────────────────────
    history: list[dict] = []
    if request.session_id:
        result = await db.execute(
            sa_select(ChatMessage)
            .where(ChatMessage.session_id == uuid.UUID(request.session_id))
            .order_by(ChatMessage.sent_at)
            .limit(20)
        )
        history = [
            {"role": row.role, "content": row.content}
            for row in result.scalars().all()
            if row.role in ("user", "assistant")
        ]

    # ── Kullanıcı sağlık koşullarını dönüştür ──────────────────────────────
    health_ctx = [
        HealthConditionCtx(
            condition_type=c.condition_type,
            severity=c.severity,
            affected_region=c.affected_region,
        )
        for c in current_user.health_conditions
        if c.is_active
    ]

    # ── Aktif plan bağlamı (opsiyonel) ────────────────────────────────────
    plan_ctx = None
    if request.plan_name:
        plan_ctx = ActivePlanCtx(
            plan_name=request.plan_name,
            sessions_per_week=request.sessions_per_week or 3,
            primary_goal=request.primary_goal or current_user.primary_goal,
            current_week=request.current_week or 1,
            current_week_exercises=request.current_week_exercises,
        )

    # ── LLM çağrısı ──────────────────────────────────────────────────────
    try:
        out = await chat_with_coach(ChatInput(
            user_id=str(current_user.id),
            user_name=current_user.full_name,
            message=request.message,
            session_id=request.session_id,
            health_conditions=health_ctx,
            active_plan=plan_ctx,
            history=history,
            preferred_provider=request.preferred_provider,
        ))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # ── Oturum yoksa oluştur ──────────────────────────────────────────────
    if not request.session_id:
        session_title = request.message[:80] + ("…" if len(request.message) > 80 else "")
        db.add(ChatSession(
            id=uuid.UUID(out.session_id),
            user_id=current_user.id,
            plan_id=None,
            session_title=session_title,
            is_active=True,
        ))

    # ── Her iki mesajı DB'ye kaydet ───────────────────────────────────────
    db.add(ChatMessage(
        session_id=uuid.UUID(out.session_id),
        **out.user_db_row(),
    ))
    db.add(ChatMessage(
        session_id=uuid.UUID(out.session_id),
        **out.assistant_db_row(),
    ))
    await db.commit()

    # ── Yanıt ────────────────────────────────────────────────────────────
    return {
        "reply":         out.reply,
        "session_id":    out.session_id,
        "tokens_used":   out.tokens_used,
        "provider_used": out.provider_used,
        # Egzersiz değişikliği talep edildiyse frontend bunu işler
        "plan_update": (
            {
                "action":       out.plan_update.action,
                "old_exercise": out.plan_update.old_exercise,
                "new_exercise": out.plan_update.new_exercise,
                "reason":       out.plan_update.reason,
                "sets":         out.plan_update.sets,
                "reps":         out.plan_update.reps,
                "rest_seconds": out.plan_update.rest_seconds,
            }
            if out.plan_update else None
        ),
    }


# ════════════════════════════════════════════════════════
#  POST /analysis/posture/compare — Aylık Gelişim Raporu
# ════════════════════════════════════════════════════════

@app.post(
    "/analysis/posture/compare",
    summary="Aylık postür gelişim karşılaştırması",
    tags=["analiz"],
    responses={
        200: {"description": "Gelişim raporu üretildi."},
        404: {"description": "Baseline analiz kaydı bulunamadı."},
        422: {"description": "Yeni fotoğrafta pose tespit edilemedi."},
    },
)
async def compare_posture_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    new_photo: UploadFile = File(..., description="Bu aydaki fotoğraf (JPG/PNG)"),
    angle: str = Form("front", description="front | back | left | right"),
    new_month_number: int = Form(..., description="Bu fotoğraf kaçıncı aya ait? (2, 3, 4...)"),
    baseline_month: int = Form(1, description="Karşılaştırılacak baz ay (genellikle 1)"),
    preferred_provider: str = Form("auto"),
):
    """
    Gelişim karşılaştırma akışı:
    1. DB'den baseline (baz ay) analiz kaydını çeker.
    2. Yeni fotoğrafı cv_service ile analiz eder.
    3. Metrikleri karşılaştırıp delta hesaplar.
    4. LLM ile Türkçe gelişim raporu üretir.
    5. Yeni analizi DB'ye kaydeder.
    """
    from sqlalchemy import select as sa_select

    # ── Dosya validasyonu ─────────────────────────────────────────────────
    if angle not in ("front", "back", "left", "right"):
        raise HTTPException(status_code=422, detail="Geçersiz açı. front/back/left/right kullanın.")
    if new_photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="Sadece JPG, PNG veya WebP kabul edilir.")

    photo_bytes = await new_photo.read()
    if len(photo_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya 10 MB'dan büyük olamaz.")

    # ── Baseline analizi DB'den çek ───────────────────────────────────────
    baseline_row = await db.execute(
        sa_select(PhotoAnalysis)
        .join(ProgressPhoto, PhotoAnalysis.photo_id == ProgressPhoto.id)
        .where(
            ProgressPhoto.user_id == current_user.id,
            ProgressPhoto.photo_angle == angle,
            ProgressPhoto.month_number == baseline_month,
        )
        .order_by(PhotoAnalysis.analyzed_at.desc())
        .limit(1)
    )
    baseline_analysis = baseline_row.scalar_one_or_none()

    if not baseline_analysis:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Ay {baseline_month} için '{angle}' açısında baseline analiz kaydı bulunamadı. "
                "Önce /analysis/posture/single endpoint'i ile başlangıç fotoğrafınızı yükleyin."
            ),
        )

    # BaselineMetrics nesnesi oluştur
    bm = baseline_analysis.body_measurements or {}
    baseline = BaselineMetrics(
        posture_score=float(baseline_analysis.posture_score or 0),
        month_number=baseline_month,
        photo_angle=angle,
        shoulder_tilt_deg=bm.get("shoulder_tilt_deg"),
        hip_tilt_deg=bm.get("hip_tilt_deg"),
        spine_lateral_dev_deg=bm.get("spine_lateral_dev_deg"),
        head_forward_deg=bm.get("head_forward_deg"),
        torso_lean_deg=bm.get("torso_lean_deg"),
        shoulder_width_ratio=bm.get("shoulder_width_ratio"),
    )

    # ── Karşılaştırmayı çalıştır ──────────────────────────────────────────
    result = await compare_posture(CompareInput(
        user_id=str(current_user.id),
        user_name=current_user.full_name,
        new_photo_bytes=photo_bytes,
        photo_angle=angle,
        new_month_number=new_month_number,
        baseline=baseline,
        preferred_provider=preferred_provider,
    ))

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error_message)

    # ── Yeni fotoğraf kaydı oluştur ───────────────────────────────────────
    new_photo_row = ProgressPhoto(
        user_id=current_user.id,
        photo_angle=angle,
        storage_path=f"users/{current_user.id}/photos/month_{new_month_number}_{angle}.jpg",
        storage_bucket="fitness-app-photos",
        month_number=new_month_number,
        weight_at_time_kg=None,     # Kullanıcı ileride ekleyebilir
    )
    db.add(new_photo_row)
    await db.flush()  # ID'yi al

    # ── Yeni analiz kaydını DB'ye yaz ─────────────────────────────────────
    payload = result.new_analysis_db_payload.copy()
    db.add(PhotoAnalysis(
        photo_id=new_photo_row.id,
        posture_landmarks=payload.get("posture_landmarks"),
        body_measurements=payload.get("body_measurements"),
        posture_score=result.new_posture_score,
        comparison_delta=payload.get("comparison_delta"),   # Delta JSONB burada!
    ))
    await db.commit()

    # ── Yanıt ────────────────────────────────────────────────────────────
    d = result.delta
    return {
        "summary": result.summary_text(),
        "scores": {
            "baseline_month":  baseline_month,
            "new_month":       new_month_number,
            "baseline_score":  d.posture_score.baseline_value,
            "new_score":       d.posture_score.new_value,
            "score_change":    d.posture_score.delta,
            "score_change_pct": d.posture_score.change_pct,
        },
        "metrics": result.delta.to_dict(),
        "improved_count":  result.delta.improved_count(),
        "worsened_count":  result.delta.worsened_count(),
        "ai_report":       result.report,   # LLM'in ürettiği JSON raporu
        "new_warnings":    result.delta.posture_score.new_value and [],   # Boş liste default
    }
