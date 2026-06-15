# SleepReach — Architecture Document

## 1. System Overview

**SleepReach** is a HIPAA-compliant lead management and patient intake platform built for **The Insomnia and Sleep Institute of Arizona** (ISAI). It automates the capture, scoring, follow-up, and conversion of sleep therapy patient leads from multiple sources including a website widget, Jotform forms, referrals, and manual entry.

### What It Does
- **Captures leads** from website widget, Jotform webhooks, referrals, and manual entry
- **Scores and prioritizes** leads based on 8 clinical/insurance/urgency factors
- **Automates follow-up** via HIPAA-compliant email (Paubox) and SMS (Twilio)
- **Provides AI insights** using OpenAI (gpt-4o) for lead analysis and coordinator recommendations
- **Manages the full patient pipeline** from initial inquiry through treatment start
- **Tracks referring providers** with conversion analytics
- **Ensures HIPAA compliance** with encrypted PHI, audit logging, and role-based access

### Who It Serves
- **Care Coordinators** — manage leads, make calls via 3CX, send follow-ups
- **Administrators** — oversee operations, view analytics, manage users
- **Primary Admins** — full system access including user management and settings
- **Referring Providers** — tracked for referral analytics and communication

---

## 2. Architecture Diagram

```
Internet
   │
   ├── app.sleeplessinarizona.com ──┐
   ├── api.sleeplessinarizona.com ──┼── AWS ACM (*.sleeplessinarizona.com)
   └── stg.sleeplessinarizona.com ──┘         │
                                              ▼
                              ┌─────────────────────────┐
                              │  Application Load        │
                              │  Balancer (shared)       │
                              │  SleepReach-ai-alb       │
                              │  Port 443 (HTTPS)        │
                              │  Port 80 → 301 redirect  │
                              └──────────┬──────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
    app.sleepless...            api.sleepless...           stg.sleepless...
              │                          │                          │
    ┌─────────▼──────┐        ┌─────────▼──────┐        ┌─────────▼──────┐
    │  Frontend TG   │        │  Backend TG    │        │  Stg Frontend  │
    │  Port 80       │        │  Port 8000     │        │  Port 80       │
    │  Health: /     │        │  Health: /     │        │  Health: /     │
    └────────────────┘        │  health/live   │        └────────────────┘
                              └────────────────┘
              │                          │                          │
    ┌─────────▼──────────────────────────▼──────────────────────────▼─────────┐
    │                    ECS Cluster: sleepreach-cluster                       │
    │                    (AWS Fargate, us-east-2)                              │
    │                                                                         │
    │  Production Services:              Staging Services:                    │
    │  ├─ sleepreach-prod-backend        ├─ sleepreach-stg-backend            │
    │  │  (FastAPI, port 8000)           │  (FastAPI, port 8000)              │
    │  ├─ sleepreach-prod-frontend       ├─ sleepreach-stg-frontend           │
    │  │  (Nginx+React, port 80)         │  (Nginx+React, port 80)            │
    │  └─ sleepreach-prod-celery         └─ sleepreach-stg-celery             │
    │     (Worker + Beat)                   (Worker + Beat)                   │
    └─────────────────────┬──────────────────────┬───────────────────────────┘
                          │                      │
         ┌────────────────┼──────────────────────┼────────────────┐
         │                │                      │                │
    ┌────▼─────┐   ┌──────▼──────┐    ┌─────────▼────┐   ┌───────▼──────┐
    │ RDS      │   │ ElastiCache │    │ Secrets       │   │ CloudWatch   │
    │ Postgres │   │ Redis 7.1   │    │ Manager       │   │ Dashboard    │
    │ 14.15    │   │ (TLS)       │    │               │   │ + 4 Alarms   │
    └──────────┘   └─────────────┘    └───────────────┘   └──────────────┘
```

---

## 3. Services

| Service | Technology | Port | Purpose |
|---------|-----------|------|---------|
| **Frontend** | React 18 + Vite + Tailwind, served by Nginx | 80 | Coordinator dashboard SPA |
| **Backend** | Python FastAPI + Uvicorn | 8000 | REST API, webhooks, lead processing |
| **Celery Worker** | Celery 5 with Redis broker | — | Async task processing (leads, emails, SMS) |
| **Celery Beat** | Runs in same container as worker | — | 7 scheduled tasks (follow-ups, digests, cache) |
| **PostgreSQL** | RDS PostgreSQL 14.15 | 5432 | Primary data store with encrypted PHI |
| **Redis** | ElastiCache Redis 7.1 (TLS) | 6379 | Cache, Celery broker, rate limiting |

---

## 4. AWS Infrastructure

### Compute — ECS Fargate
| Service | CPU | Memory | Task Definition |
|---------|-----|--------|-----------------|
| sleepreach-prod-backend | 256 | 512MB | sleepreach-prod-backend:2 |
| sleepreach-prod-frontend | 256 | 512MB | sleepreach-prod-frontend:1 |
| sleepreach-prod-celery | 256 | 512MB | sleepreach-prod-celery:1 |
| sleepreach-stg-backend | 256 | 512MB | sleepreach-stg-backend:1 |
| sleepreach-stg-frontend | 256 | 512MB | sleepreach-stg-frontend:1 |
| sleepreach-stg-celery | 256 | 512MB | sleepreach-stg-celery:1 |

### Database — RDS PostgreSQL 14
| Instance | Endpoint | Encrypted | Backup |
|----------|----------|-----------|--------|
| sleepreach-prod-db | sleepreach-prod-db.cfggkciq6tun.us-east-2.rds.amazonaws.com:5432 | ✅ AES-256 | 7 days |
| sleepreach-stg-db | sleepreach-stg-db.cfggkciq6tun.us-east-2.rds.amazonaws.com:5432 | ✅ AES-256 | 3 days |

### Cache — ElastiCache Redis 7.1
| Instance | Type | TLS |
|----------|------|-----|
| sleepreach-prod-redis | cache.t3.micro | ✅ rediss:// |
| sleepreach-stg-redis | cache.t3.micro | ✅ rediss:// |

### Networking
- **VPC:** vpc-00bed95435b092a79 (shared with SleepReach, 10.0.0.0/16)
- **ALB:** SleepReach-ai-alb (shared, HTTPS:443 + HTTP:80→301)
- **ACM Certificate:** *.sleeplessinarizona.com (ISSUED, auto-renewing)
- **Security Groups:**
  - `sg-0edebbac3eb66c47a` — ECS tasks (inbound from ALB only)
  - `sg-08abf0d99874ca3cb` — RDS (inbound from ECS SG on 5432)
  - `sg-0def53df8f192c482` — Redis (inbound from ECS SG on 6379)

### Container Registry — ECR
- `131880217305.dkr.ecr.us-east-2.amazonaws.com/sleepreach/backend`
- `131880217305.dkr.ecr.us-east-2.amazonaws.com/sleepreach/frontend`

### Secrets Manager
- `sleepreach/production` — Production credentials (DB, Paubox, Twilio, OpenAI, encryption keys)
- `sleepreach/staging` — Staging credentials

### Monitoring — CloudWatch
- **Dashboard:** SleepReach-Production (8 widgets)
- **Alarms (4):** Backend CPU, Backend Memory, ALB 5xx, RDS CPU
- **SNS Topic:** sleepreach-production-alerts → emwaniki@tmsinstitute.co
- **Log Groups:** /ecs/sleepreach-prod-*, /ecs/sleepreach-stg-* (30-day retention)

---

## 5. Domain Routing

| Domain | ALB Rule | Target Group | Service |
|--------|----------|-------------|---------|
| app.sleeplessinarizona.com | Host header match | sleepreach-prod-frontend (port 80) | React dashboard |
| api.sleeplessinarizona.com | Host header match | sleepreach-prod-backend (port 8000) | FastAPI backend |
| stg.sleeplessinarizona.com | Host header match | sleepreach-stg-frontend (port 80) | Staging dashboard |

All HTTP traffic (port 80) → 301 redirect to HTTPS (port 443).

---

## 6. Database Schema

### Tables
| Table | Purpose |
|-------|---------|
| `leads` | Patient intake leads with encrypted PHI (BYTEA columns) |
| `audit_logs` | HIPAA-compliant audit trail for all PHI access |
| `users` | System users (coordinators, admins) |
| `user_preferences` | Notification preferences per user |
| `clinic_settings` | Key-value clinic configuration |
| `referring_providers` | Referring physicians with conversion tracking |
| `lead_notes` | Notes on leads by coordinators |
| `provider_notes_history` | Notes on referring providers |
| `lead_attachments` | File attachments on leads |
| `password_reset_tokens` | Secure password reset flow |
| `invitation_requests` | User invitation workflow |

### Enums (16 total)
`condition_type`, `duration_type`, `treatment_type`, `urgency_type`, `priority_type`, `lead_status`, `audit_action`, `contact_outcome_type`, `contact_method`, `lead_source`, `user_role`, `user_status`, `provider_specialty`, `provider_status`, `provider_contact_method`

### Key Indexes (20+)
Performance indexes on: lead_number, priority, status, created_at, zip_code, in_service_area, condition, score, deleted_at, source, contact_outcome, is_referral, and composite indexes for common query patterns.

### PHI Encryption
- `first_name_encrypted`, `last_name_encrypted`, `email_encrypted`, `phone_encrypted` — stored as BYTEA using Fernet (AES-256-CBC) encryption
- Encryption key stored in AWS Secrets Manager, never in code
- Row Level Security (RLS) enabled on `leads` and `audit_logs`

---

## 7. Authentication & Authorization

- **JWT Tokens** — 30-minute access tokens, 7-day refresh tokens
- **Password Security** — bcrypt hashing, must-change-on-first-login, expiration support
- **Roles:**

| Role | Permissions |
|------|------------|
| `primary_admin` | Full access — users, settings, all leads, all analytics |
| `administrator` | Manage users, view all leads, analytics, settings |
| `coordinator` | Manage assigned leads, send follow-ups, view own analytics |
| `specialist` | View assigned leads, limited write access |

---

## 8. Email System

- **Primary:** Paubox Email API (HIPAA-compliant, TLS-encrypted delivery)
- **Fallback:** SMTP (Gmail) when Paubox is unavailable
- **Mode Control:** `EMAIL_MODE` env var — `paubox` (production), `maildev` (local dev)
- **From:** `The Insomnia and Sleep Institute of Arizona <info@sleeplessinarizona.com>`
- **Templates:** Follow-up, Appointment Confirmation, Missed Call, Thank You, Final Outreach, Custom
- **Branding:** Clinic logo, address (8330 E Hartford Drive, Suite 100, Scottsdale, AZ 85255), phone (480) 745-3547, HIPAA footer

---

## 9. SMS System

- **Provider:** Twilio
- **Phone Number:** +18337371070
- **Mode Control:** `SMS_MODE` env var — `twilio` (production), `local` (dev server)
- **Templates (5):**
  - `lead_receipt` — Initial acknowledgment
  - `follow_up` — General follow-up
  - `appointment_reminder` — Appointment reminder
  - `missed_call` — Missed call notification
  - `not_interested_follow_up` — Final outreach

---

## 10. AI Integration

- **Provider:** OpenAI (gpt-4o)
- **Features:**
  - AI Insights dashboard — trend analysis, recommendations
  - AI-recommended emails — context-aware draft emails for coordinators
  - Coordinator performance insights — efficiency metrics and suggestions
- **Caching:** 1-hour TTL in Redis to minimize API costs
- **Config:** `OPENAI_API_KEY` in Secrets Manager, model configurable via `OPENAI_MODEL`

---

## 11. Lead Pipeline

```
Source (Widget/Jotform/Referral/Manual)
    │
    ▼
Webhook/API Endpoint
    │
    ▼
Deduplication Check (email + phone hash)
    │
    ▼
PHI Encryption (Fernet AES-256)
    │
    ▼
Lead Scoring (8 components)
    ├── Condition Score (Insomnia, Sleep Apnea, etc.)
    ├── Therapy Interest Score
    ├── Severity Score
    ├── Insurance Score
    ├── Duration Score
    ├── Treatment History Score
    ├── Location Score (AZ zip: 85xxx, 86xxx)
    └── Urgency Score (ASAP > 30 days > Exploring)
    │
    ▼
Priority Assignment (HOT / MEDIUM / LOW / DISQUALIFIED)
    │
    ▼
Celery Queue (leads.high) → Async Processing
    │
    ├── Confirmation Email (Paubox)
    ├── Confirmation SMS (Twilio)
    ├── Dashboard Notification
    └── Audit Log Entry
    │
    ▼
Automated Follow-Up Drip (5 stages over weeks)
    │
    ▼
Coordinator Dashboard → Manual Follow-up → Conversion
```

---

## 12. Celery Task System

### Queues
| Queue | Priority | Purpose |
|-------|----------|---------|
| `leads.high` | 10 | Real-time lead ingestion |
| `leads.normal` | 5 | Standard lead processing |
| `leads.batch` | 1 | Batch operations |
| `default` | — | General tasks |
| `dlq` | — | Dead letter queue (failed tasks) |
| `elasticsearch` | — | Search index sync (if enabled) |

### Scheduled Tasks (Beat)
| Task | Schedule | Purpose |
|------|----------|---------|
| Dead letter queue cleanup | Every 5 min | Retry/discard failed tasks |
| Dashboard cache warming | Every 1 min | Keep dashboard fast |
| Elasticsearch sync check | Every 10 min | Index consistency |
| Platform analytics refresh | Every 5 min | Update analytics views |
| Daily lead digest | 7:00 AM MST | Daily summary email |
| Automated follow-ups | Every 6 hours | Drip campaign execution |
| Not-interested follow-ups | Mondays, 8 AM MST | Final outreach |

### Retry Strategy
- Max retries: 5
- Exponential backoff: 1s → 2s → 4s → 8s → 16s
- Failed tasks → Dead Letter Queue → Cleanup every 5 minutes

---

## 13. Security & HIPAA Compliance

| Control | Implementation |
|---------|---------------|
| **PHI Encryption** | Fernet (AES-256-CBC) for names, email, phone in DB |
| **Encryption at Rest** | RDS AES-256, ElastiCache TLS |
| **Encryption in Transit** | HTTPS (ACM TLS 1.2+), Redis TLS (rediss://) |
| **Audit Logging** | All PHI access logged to `audit_logs` table |
| **Row Level Security** | RLS policies on `leads` and `audit_logs` |
| **Access Control** | JWT + role-based (4 roles) |
| **Rate Limiting** | 60/min unauth, 300/min auth, 1000/min webhooks |
| **CORS** | Configurable allowed origins |
| **Password Policy** | bcrypt hash, must-change-on-first-login, expiration |
| **Secrets Management** | AWS Secrets Manager (never in code) |
| **Network Isolation** | Private subnets for RDS/Redis, SG whitelisting |

---

## 14. Monitoring

### CloudWatch Dashboard
**URL:** https://us-east-2.console.aws.amazon.com/cloudwatch/home?region=us-east-2#dashboards/dashboard/SleepReach-Production

### Alarms
| Alarm | Threshold | Action |
|-------|-----------|--------|
| sleepreach-prod-backend-cpu-high | CPU > 80% for 5 min | SNS alert |
| sleepreach-prod-backend-memory-high | Memory > 80% for 5 min | SNS alert |
| sleepreach-prod-alb-5xx-errors | 5xx > 10 in 5 min | SNS alert |
| sleepreach-prod-rds-cpu-high | CPU > 80% for 5 min | SNS alert |

### Health Endpoints
| Endpoint | Checks | Use |
|----------|--------|-----|
| `GET /health` | API + Database | ALB health check (primary) |
| `GET /health/ready` | DB + Redis + Queue depths | Deep readiness check |
| `GET /health/live` | API process alive | ALB liveness probe |

---

## 15. Cost Breakdown (Monthly)

| Service | Cost |
|---------|------|
| ECS Fargate (6 tasks × 0.25 vCPU, 512MB) | ~$40 |
| RDS db.t3.micro × 2 (prod + stg) | ~$30 |
| ElastiCache cache.t3.micro × 2 | ~$24 |
| ALB (shared with SleepReach) | ~$8 |
| CloudWatch (dashboard + alarms + logs) | ~$5 |
| ECR (container images) | ~$1 |
| **Total** | **~$108/month** |
