# SleepReach — Operations Runbook

> **Last updated:** 2026-04-21  
> **AWS Account:** 131880217305 (us-east-2)  
> **Repo:** `https://github.com/EvanMaina/SleepReach.git`

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [How to Deploy to Staging](#2-how-to-deploy-to-staging)
3. [How to Deploy to Production](#3-how-to-deploy-to-production)
4. [How to Rollback](#4-how-to-rollback)
5. [How to Run Manual Backup](#5-how-to-run-manual-backup)
6. [How to Restore from Backup](#6-how-to-restore-from-backup)
7. [Monitoring & CloudWatch](#7-monitoring--cloudwatch)
8. [Alarm Escalation Procedures](#8-alarm-escalation-procedures)
9. [Health Check Endpoints](#9-health-check-endpoints)
10. [Useful Commands](#10-useful-commands)

---

## 1. Pipeline Overview

### Deployment Flow (Controlled Promotion)

```
┌─────────────────────────────────────────────────────────┐
│  LOCAL (dev branch)                                      │
│  1. Code changes                                        │
│  2. Test locally: docker-compose up                     │
│  3. git add + commit + push origin dev                  │
│  4. CI runs automatically (lint, test, build, scan)     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  STAGING (stg branch)                                    │
│  5. Merge dev → stg (PR or direct)                      │
│  6. Push to stg triggers deploy-staging.yml             │
│  7. Verify on https://stg.sleeplessinarizona.com        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  PRODUCTION (main branch)                                │
│  8. Merge stg → main (PR recommended)                   │
│  9. Push to main triggers deploy-production.yml         │
│  10. Verify on https://app.sleeplessinarizona.com       │
│  11. Auto-tagged: deploy-prod-<sha>-<timestamp>         │
└─────────────────────────────────────────────────────────┘
```

### Workflow Files

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `ci.yml` | Push to `dev`, PRs to `dev/stg/main` | Lint, test, build, security scan |
| **Deploy Staging** | `deploy-staging.yml` | Push to `stg`, manual | Build + deploy to staging ECS |
| **Deploy Production** | `deploy-production.yml` | Push to `main`, manual | Build + deploy to production ECS |
| **Rollback** | `rollback.yml` | Manual only | Revert production to previous version |
| **Backup** | `backup.yml` | Daily 02:00 UTC, Weekly Sun 04:00 UTC, manual | pg_dump → S3 |
| ~~Promote~~ | `promote.yml` | **DISABLED** | Was auto-promote; replaced by branch triggers |

> **Important:** The old `promote.yml` auto-promoted from dev all the way to production in one shot. It is now **disabled**. Use branch merges instead.

---

## 2. How to Deploy to Staging

### Option A: Direct merge (fastest)

```bash
git checkout dev
# ... make changes, test locally ...
git add . && git commit -m "feat: description"
git push origin dev      # CI runs

git checkout stg
git merge dev
git push origin stg      # → triggers deploy-staging.yml automatically
```

### Option B: Pull Request

```bash
git push origin dev
gh pr create --base stg --head dev --title "Deploy to staging"
gh pr merge <PR-NUMBER> --merge
# → triggers deploy-staging.yml automatically
```

### Monitor deployment

```bash
gh run list --workflow deploy-staging.yml --repo EvanMaina/SleepReach --limit 3
gh run watch --repo EvanMaina/SleepReach
```

### Verify staging

```bash
curl -sf https://stg.sleeplessinarizona.com/health | python -m json.tool
```

---

## 3. How to Deploy to Production

### Recommended: Pull Request from stg → main

```bash
gh pr create --base main --head stg --title "Deploy to production" --body "Staging verified ✅"
gh pr merge <PR-NUMBER> --merge
# → triggers deploy-production.yml automatically
```

### Emergency: Direct merge

```bash
git checkout main
git merge stg
git push origin main     # → triggers deploy-production.yml
```

### Manual trigger (no code change)

```bash
gh workflow run "Deploy to Production" --repo EvanMaina/SleepReach
```

### Verify production

```bash
curl -sf https://api.sleeplessinarizona.com/health | python -m json.tool
curl -sf https://app.sleeplessinarizona.com -o /dev/null -w "%{http_code}\n"
```

---

## 4. How to Rollback

### Option 1: GitHub Actions UI (recommended)

1. Go to **GitHub Actions** → **🔄 Rollback Production**
2. Click **"Run workflow"**
3. Choose method:
   - `previous-task-definition` — reverts to the ECS task def before the current one
   - `specific-image-tag` — specify an ECR tag like `prod-c24c8a2`
4. Choose scope: `both`, `backend-only`, or `celery-only`
5. Type `ROLLBACK` to confirm
6. Click **"Run workflow"**

### Option 2: CLI

```bash
gh workflow run rollback.yml --repo EvanMaina/SleepReach \
  -f rollback_type=previous-task-definition \
  -f services=both \
  -f confirm=ROLLBACK
```

### Option 3: AWS CLI (direct)

```bash
# Get current revision
aws ecs describe-services --cluster sleepreach-cluster \
  --services sleepreach-prod-backend \
  --query 'services[0].taskDefinition' --output text --region us-east-2

# Roll back to previous revision (e.g., from :35 to :34)
aws ecs update-service --cluster sleepreach-cluster \
  --service sleepreach-prod-backend \
  --task-definition sleepreach-prod-backend:34 \
  --force-new-deployment --region us-east-2

aws ecs wait services-stable --cluster sleepreach-cluster \
  --services sleepreach-prod-backend --region us-east-2
```

### Option 4: Git revert + redeploy

```bash
git checkout main
git revert HEAD
git push origin main
# → deploy-production.yml triggers automatically
```

---

## 5. How to Run Manual Backup

### Via GitHub Actions

```bash
gh workflow run backup.yml --repo EvanMaina/SleepReach -f backup_type=daily
```

### Verify backup

```bash
aws s3 ls s3://sleepreach-backups-prod/rds/daily/$(date -u +%Y/%m/%d)/ --region us-east-2
```

### Automated schedule

| Type | Schedule | Cron |
|------|----------|------|
| Daily | Mon-Sat 02:00 UTC | `0 2 * * *` |
| Weekly | Sunday 04:00 UTC | `0 4 * * 0` |

---

## 6. How to Restore from Backup

> ⚠️ **CAUTION:** Test restores on **staging** first. Never restore directly to production without testing.

```bash
# 1. Download backup from S3
aws s3 cp s3://sleepreach-backups-prod/rds/daily/2026/04/21/sleepreach_*.sql.gz ./backup.sql.gz --region us-east-2

# 2. Decompress
gunzip backup.sql.gz

# 3. Restore to staging DB first
psql -h <staging-rds-endpoint> -U <username> -d sleepreach_staging < backup.sql

# 4. Verify
psql -h <staging-rds-endpoint> -U <username> -d sleepreach_staging -c "SELECT count(*) FROM leads;"

# 5. If verified, restore to production (during maintenance window)
psql -h <production-rds-endpoint> -U <username> -d sleepreach_production < backup.sql
```

### AWS RDS Snapshots (alternative)

```bash
# List available snapshots
aws rds describe-db-snapshots --db-instance-identifier sleepreach-prod-db \
  --query "DBSnapshots[*].{id:DBSnapshotIdentifier,time:SnapshotCreateTime}" \
  --output table --region us-east-2
```

---

## 7. Monitoring & CloudWatch

### Dashboard

**URL:** [SleepReach Production Dashboard](https://us-east-2.console.aws.amazon.com/cloudwatch/home?region=us-east-2#dashboards:name=SleepReach-Production)

The dashboard shows:
- ECS service CPU & memory utilization (all services)
- ALB request count, 5XX/4XX errors, response times (p50/p95/p99)
- RDS CPU, connections, free storage, read/write latency
- Redis CPU and memory utilization
- ECS running task count

### CloudWatch Log Groups

| Log Group | Service |
|-----------|---------|
| `/ecs/sleepreach-prod-backend` | Production backend |
| `/ecs/sleepreach-prod-frontend` | Production frontend |
| `/ecs/sleepreach-prod-celery` | Production Celery worker |
| `/ecs/sleepreach-stg-backend` | Staging backend |
| `/ecs/sleepreach-stg-frontend` | Staging frontend |
| `/ecs/sleepreach-stg-celery` | Staging Celery worker |

### View logs

```bash
# Follow production backend logs
aws logs tail /ecs/sleepreach-prod-backend --follow --region us-east-2

# Last 30 minutes
aws logs tail /ecs/sleepreach-prod-backend --since 30m --region us-east-2

# Search for errors
aws logs filter-log-events \
  --log-group-name /ecs/sleepreach-prod-backend \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s000) \
  --region us-east-2
```

---

## 8. Alarm Escalation Procedures

### Active Alarms

| Alarm | Condition | Severity | Action |
|-------|-----------|----------|--------|
| `sleepreach-prod-5xx-high` | >10 5XX errors in 5 min | 🔴 Critical | Check backend logs, consider rollback |
| `sleepreach-prod-latency-high` | p99 > 5s for 5 min | 🟡 Warning | Check DB connections, Redis, task CPU |
| `sleepreach-prod-rds-cpu-high` | CPU > 80% for 10 min | 🟡 Warning | Check slow queries, connection count |
| `sleepreach-prod-rds-storage-low` | Free storage < 1 GB | 🔴 Critical | Increase storage immediately |
| `sleepreach-prod-redis-memory-high` | Memory > 80% | 🟡 Warning | Clear stale cache, increase instance |
| `sleepreach-prod-backend-task-low` | No running tasks for 2 min | 🔴 Critical | Check ECS events, force new deployment |

### SNS Topic

Alarms notify: `arn:aws:sns:us-east-2:131880217305:sleepreach-production-alerts`

### Escalation flow

1. **Alert fires** → Check CloudWatch dashboard
2. **Identify scope** → Is it backend? DB? Network?
3. **If 5XX spike:**
   - Check backend logs: `aws logs tail /ecs/sleepreach-prod-backend --follow`
   - If caused by bad deploy → **Rollback** (see Section 4)
   - If DB issue → Check RDS metrics, connections
4. **If latency spike:**
   - Check RDS CPU and connection count
   - Check Redis connectivity
   - Check ECS task CPU/memory
5. **If task count drops to 0:**
   - Check ECS service events: `aws ecs describe-services --cluster sleepreach-cluster --services sleepreach-prod-backend`
   - Force new deployment: `aws ecs update-service --cluster sleepreach-cluster --service sleepreach-prod-backend --force-new-deployment`

---

## 9. Health Check Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | Full health check (DB + Redis) | `{"status": "healthy", ...}` |
| `GET /health/live` | Liveness probe | `{"status": "alive"}` |
| `GET /health/ready` | Readiness probe | `{"status": "ready"}` |
| `GET /health/notifications` | Notification services check | Service connectivity status |

### Quick health check

```bash
# Production
curl -sf https://api.sleeplessinarizona.com/health | python -m json.tool

# Staging
curl -sf https://stg.sleeplessinarizona.com/health | python -m json.tool
```

---

## 10. Useful Commands

### Deployment

```bash
# Check CI status
gh run list --repo EvanMaina/SleepReach

# Watch a running workflow
gh run watch --repo EvanMaina/SleepReach

# Trigger manual staging deploy
gh workflow run "Deploy to Staging" --repo EvanMaina/SleepReach

# Trigger manual production deploy
gh workflow run "Deploy to Production" --repo EvanMaina/SleepReach
```

### AWS ECS

```bash
# List all services
aws ecs describe-services --cluster sleepreach-cluster \
  --services sleepreach-prod-backend sleepreach-prod-celery sleepreach-prod-frontend \
  --query 'services[*].{name:serviceName,status:status,desired:desiredCount,running:runningCount,taskDef:taskDefinition}' \
  --output table --region us-east-2

# Force new deployment (restart tasks)
aws ecs update-service --cluster sleepreach-cluster \
  --service sleepreach-prod-backend \
  --force-new-deployment --region us-east-2

# View ECS service events (troubleshooting)
aws ecs describe-services --cluster sleepreach-cluster \
  --services sleepreach-prod-backend \
  --query 'services[0].events[:5]' --output table --region us-east-2
```

### ECR

```bash
# List recent production images
aws ecr describe-images --repository-name sleepreach/backend \
  --query 'imageDetails[?imageTags[?starts_with(@,`prod-`)]].{tags:imageTags,pushed:imagePushedAt}' \
  --output table --region us-east-2

# List recent staging images
aws ecr describe-images --repository-name sleepreach/backend \
  --query 'imageDetails[?imageTags[?starts_with(@,`stg-`)]].{tags:imageTags,pushed:imagePushedAt}' \
  --output table --region us-east-2
```

### Database

```bash
# Check RDS status
aws rds describe-db-instances \
  --query 'DBInstances[?starts_with(DBInstanceIdentifier,`sleepreach`)].{id:DBInstanceIdentifier,status:DBInstanceStatus,class:DBInstanceClass}' \
  --output table --region us-east-2
```

---

## Quick Reference Card

| What | How |
|------|-----|
| Deploy to staging | Merge `dev → stg` |
| Deploy to production | Merge `stg → main` |
| Rollback production | GitHub Actions → "🔄 Rollback Production" |
| Run backup | GitHub Actions → "🗄️ Database Backup" |
| Check health | `curl https://api.sleeplessinarizona.com/health` |
| View logs | `aws logs tail /ecs/sleepreach-prod-backend --follow` |
| CloudWatch dashboard | [Link](https://us-east-2.console.aws.amazon.com/cloudwatch/home?region=us-east-2#dashboards:name=SleepReach-Production) |
| Run CI manually | `gh workflow run ci.yml --repo EvanMaina/SleepReach` |

---

*This runbook is part of the SleepReach repository. Keep it updated when infrastructure changes.*
