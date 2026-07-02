# FitCore AI — Full-Stack Fitness Platform

AI-powered fitness application: posture analysis via MediaPipe, GPT-4o-mini workout generation, memory-aware coaching chatbot, and monthly progress comparison — built as a Software Engineering graduation project.

---

## Architecture Overview

```
fitcore/
├── backend/          ← FastAPI (flat file structure)
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── services.py
│   ├── cv_service.py
│   ├── ai_service.py
│   ├── chat_service.py
│   ├── progress_service.py
│   └── prompts/
│       ├── workout_system.txt
│       ├── coach_persona.txt
│       └── progress_report.txt
│
└── frontend/         ← React + Tailwind CSS
    ├── public/
    │   └── index.html
    ├── src/
    │   ├── App.js
    │   ├── index.js
    │   ├── index.css
    │   ├── components/
    │   │   ├── layout/
    │   │   │   ├── DashboardLayout.jsx
    │   │   │   ├── Sidebar.jsx
    │   │   │   ├── Topbar.jsx
    │   │   │   └── MobileSidebar.jsx
    │   │   └── ui/
    │   │       ├── StatCard.jsx
    │   │       ├── ScoreRing.jsx
    │   │       ├── Spinner.jsx
    │   │       └── EmptyState.jsx
    │   ├── pages/
    │   │   ├── LoginPage.jsx
    │   │   ├── RegisterPage.jsx
    │   │   ├── DashboardOverview.jsx
    │   │   ├── ProfileHealth.jsx
    │   │   ├── PostureStudio.jsx
    │   │   ├── WorkoutEngine.jsx
    │   │   ├── CoachChat.jsx
    │   │   └── ProgressAnalytics.jsx
    │   ├── services/
    │   │   ├── api.js
    │   │   ├── authService.js
    │   │   ├── userService.js
    │   │   ├── postureService.js
    │   │   ├── workoutService.js
    │   │   └── chatService.js
    │   ├── hooks/
    │   │   └── useAuth.js
    │   └── utils/
    │       └── format.js
    ├── package.json
    ├── tailwind.config.js
    └── postcss.config.js
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| PostgreSQL | 14+ |
| npm | 9+ |

---

## Backend Setup

### 1. Create and activate virtual environment

```bash
cd backend
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 2. Install dependencies

```bash
pip install fastapi uvicorn[standard] sqlalchemy asyncpg alembic \
            pydantic pydantic-settings pydantic[email] \
            python-jose[cryptography] passlib[bcrypt] \
            mediapipe opencv-python-headless numpy \
            openai anthropic \
            python-multipart python-dotenv
```

### 3. Create `.env` file

```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/fitness_db
SECRET_KEY=your-secret-key-min-32-chars          # openssl rand -hex 32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# At least one LLM key is required:
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Create PostgreSQL database

```bash
psql -U postgres -c "CREATE DATABASE fitness_db;"
```

### 5. Run the database schema

```bash
psql -U postgres -d fitness_db -f schema.sql
# Or run the CREATE TABLE statements from the project docs directly.
```

### 6. Start the backend server

```bash
uvicorn main:app --reload --port 8000
```

Swagger UI available at: `http://localhost:8000/docs`

---

## Frontend Setup

### 1. Navigate to the frontend directory

```bash
cd frontend
```

### 2. Install dependencies

```bash
npm install
```

This installs:
- `react`, `react-dom`, `react-router-dom` — core UI
- `axios` — HTTP client for backend communication
- `tailwindcss`, `autoprefixer`, `postcss` — styling
- `recharts` — Radar + Bar charts in Progress Analytics
- `lucide-react` — icon set used throughout
- `react-dropzone` — photo upload slots in PostureStudio
- `react-hot-toast` — notification toasts
- `date-fns` — date formatting utilities
- `clsx` — conditional className helper

### 3. Create `.env` in the frontend directory (optional)

```env
REACT_APP_API_URL=http://localhost:8000
```

If not set, defaults to `http://localhost:8000` via the proxy in `package.json`.

### 4. Start the development server

```bash
npm start
```

App opens at: `http://localhost:3000`

---

## Running Both Together

Open two terminal windows:

**Terminal 1 — Backend:**
```bash
cd backend && source venv/bin/activate && uvicorn main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend && npm start
```

---

## Feature Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard Overview | Weight stats, BMI, quick action cards, active conditions summary |
| `/profile` | Profile & Health | Edit physical metrics and health conditions |
| `/posture` | Posture Analysis Studio | Upload 1–4 photos, run MediaPipe analysis, view per-angle scores and warnings |
| `/workout` | AI Workout Engine | Configure and generate a GPT-4o-mini multi-week training program |
| `/coach` | FitCoach Chat | Memory-aware coaching chatbot with PLAN_UPDATE rendering |
| `/progress` | Progress Analytics | Monthly posture comparison with delta bar chart + radar overlay |
| `/login` | Login | JWT authentication |
| `/register` | Register | 3-step: account → physical data → health conditions |

---

## Backend Endpoints Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT token |
| GET | `/users/me` | Current user profile |
| PATCH | `/users/me` | Update physical data / conditions |
| POST | `/analysis/posture/single` | Analyze one photo |
| POST | `/analysis/posture/multi` | Analyze 2–4 photos |
| POST | `/analysis/posture/compare` | Monthly progress comparison |
| POST | `/workout/generate` | AI workout plan generation |
| GET | `/workout/preview-prompt` | Debug: view LLM prompt |
| POST | `/chat/message` | Send message to FitCoach |
| GET | `/health` | Health check |

---

## Environment Notes

- **LLM provider selection**: `preferred_provider: "auto"` in both workout and chat endpoints auto-selects OpenAI if `OPENAI_API_KEY` is set, falls back to Anthropic. Set explicitly to `"openai"` or `"anthropic"` to force one.
- **Photo storage**: Currently stores to a local path string in the DB. For production, wire in AWS S3 or Cloudflare R2 — `cv_service.py` accepts raw bytes so the upload layer is separate.
- **PATCH /users/me**: Requires the `update_profile_endpoint_addition.py` to be merged into `main.py` and `services.py` — see that file for exact paste locations.
- **MediaPipe model**: Downloads automatically on first `analyze_posture()` call (~30 MB). Subsequent calls use the cached model.

---

## Production Checklist

- [ ] Change `SECRET_KEY` to a cryptographically random value
- [ ] Set `DEBUG=false` in backend config
- [ ] Restrict CORS `allow_origins` in `main.py` to your frontend domain
- [ ] Wire real S3/R2 storage for photos
- [ ] Add rate limiting to `/chat/message` (token cost control)
- [ ] Build frontend: `npm run build` → serve `build/` via nginx or Vercel
- [ ] Use `gunicorn` with `uvicorn` workers in production: `gunicorn main:app -k uvicorn.workers.UvicornWorker`

---

## Project Credits

Built as a graduation project at Istanbul Okan University, Software Engineering Department.

Backend: Python · FastAPI · PostgreSQL · SQLAlchemy · MediaPipe · OpenAI / Anthropic
Frontend: React · Tailwind CSS · Recharts · Lucide React
