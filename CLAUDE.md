# SleepReach — CLAUDE.md

HIPAA-compliant lead-management platform for The Insomnia and Sleep Institute of Arizona.
React 18 + FastAPI + PostgreSQL + Redis + Celery. Docker Compose for local dev.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, React Query |
| Backend | FastAPI (Python 3.11), SQLAlchemy 2, Pydantic v2 |
| DB | PostgreSQL 14 (via SQLAlchemy ORM) |
| Cache / Queue | Redis 7 + Celery 5 |
| Auth | JWT (FastAPI) |
| Comms | Twilio (SMS), Paubox (HIPAA email) |
| AI | OpenAI (gpt-4o) |

## Local dev (Docker Compose)

```bash
docker compose up -d          # start all services
docker compose logs -f backend
docker compose restart backend  # hot-reload Python (uvicorn --reload already on)
```

- Frontend dev server: http://localhost:5173
- Backend API:         http://localhost:8000
- API docs:            http://localhost:8000/docs
- Maildev (email UI):  http://localhost:1080
- SMS dev UI:          http://localhost:1081

Backend Python source is bind-mounted (`./backend/src`) → uvicorn auto-reloads on save.
Frontend source is bind-mounted (`./frontend/src`) → Vite HMR.

## Assessment bundle (separate build)

The patient-facing assessment form is a standalone IIFE bundle served by the backend at `/assessment`.

After editing `frontend/src/pages/AssessmentPage.tsx`:

```bash
cd frontend
npm run build:assessment          # outputs frontend/dist-assessment/assessment.js
copy dist-assessment\assessment.js ..\backend\static\assessment.js
# backend picks it up automatically (mtime check); or: docker compose restart backend
```

Widget bundle (for WP embed) works the same way:
```bash
npm run build:widget              # outputs frontend/dist-widget/widget-embed.js
```

## Key directories

```
backend/src/
  api/          # FastAPI routers (leads.py, widget.py, auth.py …)
  models/       # SQLAlchemy models (lead.py, user.py …)
  schemas/      # Pydantic schemas
  services/     # Business logic (lead_scoring_v2, intake_mapping …)
  tasks/        # Celery async tasks
  main.py       # App entry point

frontend/src/
  pages/        # CoordinatorPage.tsx, AssessmentPage.tsx …
  components/   # Reusable UI components
  contexts/     # AuthContext
  lib/api.ts    # Axios API client
  widget-entry.tsx      # WP widget IIFE entry
  assessment-entry.tsx  # Assessment IIFE entry
```

## Lead domain model

**Lead status** (linear pipeline):
`NEW → CONTACTED → SCHEDULED → CONSULTATION_COMPLETE → TREATMENT_STARTED`
(or `LOST` / `DISQUALIFIED`)

**Contact outcome** (per outreach attempt):
`NEW → ANSWERED | NO_ANSWER | UNREACHABLE | NOT_INTERESTED | CALLBACK_REQUESTED | SCHEDULED | COMPLETED`

**Priority** (AI-scored): `HOT | MEDIUM | LOW | DISQUALIFIED`

**Queue types** (coordinator sidebar):
`new | contacted | follow_up | callback | scheduled | completed | unreachable | not_interested | all`

- `contacted` queue: leads with ANSWERED status (excludes UNREACHABLE / NOT_INTERESTED)
- `unreachable` / `not_interested` have their own dedicated queues

## Backend queue filter

`backend/src/api/leads.py` → `apply_queue_filter()` — mirrors the sidebar queues.
Each `queue_type` maps to specific `Lead.contact_outcome` / `Lead.status` filters.

## PHI / HIPAA

All name/email/phone fields are Fernet-encrypted at rest.
Audit logs written to `audit_logs` table for every lead read/write.
Never log PHI fields. Do not print decrypted PHI to stdout.

## Environment

Secrets live in `backend/.env` (not committed). Key vars:
`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENCRYPTION_KEY`,
`TWILIO_*`, `PAUBOX_*`, `OPENAI_API_KEY`.

## Do not

- Commit `.env` or any key material
- Touch prod/AWS unless explicitly asked (work local Docker only)
- Skip audit logging on lead mutations
- Disable uvicorn `--reload` in development
