# SleepReach — Deployment Status (Verified 2026-04-21)

> **AWS Account:** 131880217305 (us-east-2)  
> **Product:** SleepReach (Sleep-clinic lead management)  
> **Repo:** `https://github.com/EvanMaina/SleepReach.git` (PRIVATE)

---

## Repository

| Item | Value |
|------|-------|
| **GitHub Remote** | `https://github.com/EvanMaina/SleepReach.git` |
| **Local Clone** | `c:\Users\hp\SleepReach-Clean` |
| **Branch `dev`** | `c24c8a2` |
| **Branch `stg`** | `c24c8a2` |
| **Branch `main`** | `c24c8a2` |
| **All branches synced** | ✅ Yes — same commit across all three |

---

## AWS ECS Services (`sleepreach-cluster`)

### Production

| Service | Task Definition | Image Tag | Commit | Status |
|---------|-----------------|-----------|--------|--------|
| `sleepreach-prod-backend` | `:34` | `sleepreach/backend:prod-c24c8a2` | `c24c8a2` | ✅ Running |
| `sleepreach-prod-frontend` | `:31` | `sleepreach/frontend@sha256:aa999cde…` | `c24c8a2` | ✅ Running |
| `sleepreach-prod-celery` | `:34` | `sleepreach/backend:prod-c24c8a2` | `c24c8a2` | ✅ Running |

### Staging

| Service | Task Definition | Image Tag | Commit | Status |
|---------|-----------------|-----------|--------|--------|
| `sleepreach-stg-backend` | `:25` | `sleepreach/backend:stg-c24c8a2` | `c24c8a2` | ✅ Running |
| `sleepreach-stg-frontend` | `:23` | `sleepreach/frontend:stg-c24c8a2` | `c24c8a2` | ✅ Running |
| `sleepreach-stg-celery` | `:26` | `sleepreach/backend:stg-c24c8a2` | `c24c8a2` | ✅ Running |

---

## Databases (RDS PostgreSQL)

| Instance | Class | Status | Environment |
|----------|-------|--------|-------------|
| `sleepreach-prod-db` | db.t3.micro | ✅ available | Production |
| `sleepreach-stg-db` | db.t3.micro | ✅ available | Staging |

---

## Caching (ElastiCache Redis)

| Cluster | Status | Environment |
|---------|--------|-------------|
| `sleepreach-prod-redis-tls-001` | ✅ available | Production |
| `sleepreach-stg-redis-tls-001` | ✅ available | Staging |

---

## ECR Repositories

| Repository | Used By |
|------------|---------|
| `sleepreach/backend` | Backend + Celery (same image, different entrypoint) |
| `sleepreach/frontend` | Frontend (nginx + React SPA) |

---

## Live URLs

| Environment | Frontend | Backend API | Health |
|-------------|----------|-------------|--------|
| **Production** | `https://app.sleeplessinarizona.com` | `https://api.sleeplessinarizona.com` | ✅ DB + Redis healthy |
| **Staging** | `https://stg.sleeplessinarizona.com` | via ALB | ✅ |

---

## CI/CD Workflows (GitHub Actions)

| Workflow | File | Trigger |
|----------|------|---------|
| CI | `ci.yml` | Push to `dev`, PRs |
| Auto-Promote | `promote.yml` | CI pass on `dev` → auto-deploys everything |
| Deploy Staging | `deploy-staging.yml` | Push to `stg` / called by promote |
| Deploy Production | `deploy-production.yml` | Push to `main` / called by promote |
| Rollback | `rollback.yml` | Manual (workflow_dispatch) |
| Backup | `backup.yml` | Daily 02:00 UTC, Weekly Sun 04:00 UTC |

---

## Backups

| Bucket | Schedule | Method |
|--------|----------|--------|
| `s3://sleepreach-backups-prod` | Daily + Weekly | `pg_dump` via ECS Fargate task |

---

## Key Notes

1. **All branches and all deployed services are at the SAME commit `c24c8a2`** — staging and production are in sync.
2. **The promote.yml workflow currently auto-promotes from dev all the way to production** — planned change is to disable this and use branch-triggered deploys instead (see IMPLEMENTATION_PLAN.md).
3. **Repo identity guard** (`scripts/verify_repo_identity.sh`) prevents cross-contamination with NeuroReach.
4. **Celery is pinned to desiredCount=1** to prevent duplicate Beat schedulers.
5. **Frontend production task def (:31) uses a digest-pinned image** — this was done during the cross-contamination fix to ensure the exact correct image is used.

---

*See IMPLEMENTATION_PLAN.md for the full task list to clean up and operationalize this pipeline.*
