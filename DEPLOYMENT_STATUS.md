# SleepReach — Deployment Status (Updated 2026-04-21 18:53 EAT)

> **AWS Account:** 131880217305 (us-east-2)  
> **Product:** SleepReach (Sleep-clinic lead management)  
> **Repo:** `https://github.com/EvanMaina/SleepReach.git` (PRIVATE — GitHub Pro)

---

## ✅ CI/CD Pipeline — FULLY OPERATIONAL

The pipeline has been refactored from auto-promote to **controlled branch-triggered deploys**:

```
dev → CI (lint + test)
stg → Deploy to Staging (ECS)
main → Deploy to Production (ECS)
```

### Verified Workflow Runs

| Workflow | Run ID | Status | Duration |
|----------|--------|--------|----------|
| **CI** (push to dev) | 24731446217 | ✅ Success | ~3 min |
| **Deploy to Staging** (manual trigger) | 24731547689 | ✅ Success | 15m 28s |
| **Deploy to Production** | — | Ready (trigger via merge stg→main) | — |

---

## Repository

| Item | Value |
|------|-------|
| **GitHub Remote** | `https://github.com/EvanMaina/SleepReach.git` |
| **Branch `dev`** | `ec73bf6` |
| **Branch `stg`** | `ec73bf6` |
| **Branch `main`** | `ec73bf6` |
| **All branches synced** | ✅ Yes — same commit across all three |
| **Branch Protection (main)** | ✅ Enabled (PR required, GitHub Pro) |

---

## AWS ECS Services (`sleepreach-cluster`)

### Production

| Service | Status |
|---------|--------|
| `sleepreach-prod-backend` | ✅ Running |
| `sleepreach-prod-frontend` | ✅ Running |
| `sleepreach-prod-celery` | ✅ Running (pinned to 1 replica) |

### Staging (freshly deployed via workflow)

| Service | Image Tag | Status |
|---------|-----------|--------|
| `sleepreach-stg-backend` | `stg-ec73bf6` | ✅ Running |
| `sleepreach-stg-frontend` | `stg-ec73bf6` | ✅ Running |
| `sleepreach-stg-celery` | `stg-ec73bf6` | ✅ Running |

---

## Databases (RDS PostgreSQL)

| Instance | Status | Environment |
|----------|--------|-------------|
| `sleepreach-prod-db` | ✅ available | Production |
| `sleepreach-stg-db` | ✅ available | Staging |

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
| **Production** | `https://app.sleeplessinarizona.com` | `https://api.sleeplessinarizona.com` | ✅ Healthy |
| **Staging** | `https://stg.sleeplessinarizona.com` | via ALB | ✅ Healthy (smoke tests passed) |

---

## CI/CD Workflows (GitHub Actions)

| Workflow | File | Trigger | Status |
|----------|------|---------|--------|
| CI | `ci.yml` | Push to `dev`, PRs to dev/stg/main | ✅ Verified |
| Deploy Staging | `deploy-staging.yml` | Push to `stg`, manual | ✅ Verified |
| Deploy Production | `deploy-production.yml` | Push to `main`, manual | ✅ Ready |
| Promote (DISABLED) | `promote.yml` | Disabled stub — no longer auto-promotes | ✅ Disabled |
| Rollback | `rollback.yml` | Manual (workflow_dispatch) | ✅ Available |
| Backup | `backup.yml` | Daily 02:00 UTC, Weekly Sun 04:00 UTC | ✅ Active |

---

## Monitoring (CloudWatch)

| Resource | Status |
|----------|--------|
| **Dashboard** | `SleepReach-Production` — 9 widgets (ECS, ALB, RDS, Redis) |
| **Alarms** | 15 alarms — all in OK state |
| **SNS Topic** | `arn:aws:sns:us-east-2:131880217305:sleepreach-production-alerts` |

---

## Documentation

| Document | Path |
|----------|------|
| Operations Runbook | `docs/OPERATIONS_RUNBOOK.md` |
| Architecture | `ARCHITECTURE.md` |
| Implementation Plan | `IMPLEMENTATION_PLAN.md` |
| CloudWatch Setup Script | `infrastructure/cloudwatch-setup.sh` |
| Dashboard JSON | `infrastructure/dashboard-body.json` |

---

## Key Notes

1. **Pipeline is branch-triggered**: push to `dev` → CI only; merge to `stg` → staging deploy; merge to `main` → production deploy.
2. **Branch protection on `main`** requires PRs (GitHub Pro enabled).
3. **promote.yml is DISABLED** — replaced with branch-triggered deploys.
4. **Repo identity guard** (`scripts/verify_repo_identity.sh`) prevents cross-contamination with NeuroReach.
5. **Celery is pinned to desiredCount=1** to prevent duplicate Beat schedulers.
6. **Smoke tests and identity verification** run automatically after every deploy.
7. **Production deploy** creates a git release tag automatically.

---

## How to Deploy

### To Staging
```bash
git checkout stg
git merge dev
git push origin stg
# → Triggers deploy-staging.yml automatically
```

### To Production
```bash
git checkout main
git merge stg
git push origin main
# → Triggers deploy-production.yml automatically (runs CI first)
```

### Manual Trigger
Go to **Actions** tab → Select workflow → **Run workflow**

### Rollback
Go to **Actions** tab → **Rollback** → Enter environment + image tag → Confirm with "ROLLBACK"

---

*Last updated: 2026-04-21 18:53 EAT*
