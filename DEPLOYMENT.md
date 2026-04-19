# SleepReach — Deployment Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Node.js** | 22.x | Frontend builds |
| **Python** | 3.11 | Backend runtime |
| **Docker** | 24+ | Container builds |
| **AWS CLI** | 2.x | Infrastructure management |
| **Git** | 2.x | Version control |

### AWS Access

```bash
# Configure AWS CLI with the sleepreach profile
aws configure --profile sleepreach
# Region: us-east-2
# Output: json
```

GitHub Secrets required (already configured):
- `AWS_ACCESS_KEY_ID` — IAM user access key
- `AWS_SECRET_ACCESS_KEY` — IAM user secret key

---

## Environment Setup

### Local Development

```bash
# Clone the repository
git clone https://github.com/EvanMaina/SleepReach.git
cd SleepReach

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm ci
```

### Local `.env` (backend/.env)

Your local dev environment uses **fake services** (MailDev for email, local SMS dev server). Production credentials live **only** in AWS Secrets Manager — never in code.

```env
ENVIRONMENT=development
DATABASE_URL=postgresql://sleepreach:password@localhost:5432/sleepreach
REDIS_URL=redis://localhost:6379/0
EMAIL_MODE=maildev
SMS_MODE=local
```

### Docker Compose (Local Dev)

```bash
# Start all services locally
docker-compose up -d

# Services started:
#   - PostgreSQL (port 5432)
#   - Redis (port 6379)
#   - MailDev (port 1080 — fake email UI)
#   - SMS Dev Server (port 8025 — fake SMS)
#   - Backend (port 8000)
#   - Frontend (port 3000)
```

| Service | Local URL | Purpose |
|---------|-----------|---------|
| Frontend | http://localhost:3000 | Dashboard |
| Backend API | http://localhost:8000 | API |
| MailDev | http://localhost:1080 | Fake email inbox |
| SMS Dev | http://localhost:8025 | Fake SMS viewer |
| API Docs | http://localhost:8000/docs | Swagger (dev only) |

---

## CI/CD Pipeline

### Workflows (6 total)

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `ci.yml` | Push to `dev`, PRs | Lint, typecheck, build, security scan |
| **Deploy Staging** | `deploy-staging.yml` | Push to `stg` | Build → ECR → ECS staging |
| **Deploy Production** | `deploy-production.yml` | Push to `main` | Build → ECR → ECS production |
| **Promote** | `promote.yml` | CI passes on `dev` | Auto: dev → stg → main (full pipeline) |
| **Rollback** | `rollback.yml` | Manual dispatch | Rollback production to previous revision |
| **Backup** | `backup.yml` | Daily 2AM UTC + Weekly Sunday 4AM UTC | Database backup to S3 |

### CI Checks (`ci.yml`)

Runs on every push to `dev` and all PRs:

| Check | Tool | Blocking? |
|-------|------|-----------|
| Backend Lint | Flake8 | Advisory |
| Backend Type Check | MyPy | Advisory |
| Backend Tests | Pytest | Advisory |
| Frontend Lint | ESLint | Advisory |
| **Frontend Type Check** | **TypeScript** | **Yes — must pass** |
| **Frontend Build** | **Vite** | **Yes — must pass** |
| Security Scan | Trivy | Advisory |
| Secret Scan | Gitleaks | Advisory |
| **Docker Build** | **Docker** | **Yes — must pass** |

### Automatic Promotion Flow

```
Push to dev
    │
    ▼
CI runs automatically (ci.yml)
    │
    ▼ (CI passes)
Promote workflow triggers (promote.yml)
    │
    ├── 1. Merge dev → stg
    ├── 2. Deploy to Staging (ECS)
    ├── 3. Merge stg → main
    └── 4. Deploy to Production (ECS)
```

**One push to `dev` = automatic deployment to all environments.**

---

## Deployment Flow

### Branch Strategy

```
dev (development) → stg (staging) → main (production)
```

### Step-by-Step: Deploy a Change

```bash
# 1. Make changes on dev branch
git checkout dev
# ... make changes ...
git add -A && git commit -m "feat: your change"

# 2. Push to dev — CI runs automatically
git push origin dev

# 3. If CI passes, Promote workflow auto-triggers:
#    dev → stg (deploy) → main (deploy)
#    No manual steps needed!
```

### Manual Deploy to Staging Only

```bash
git checkout stg
git merge dev
git push origin stg
# deploy-staging.yml triggers automatically
```

### Manual Deploy to Production Only

```bash
git checkout main
git merge stg
git push origin main
# deploy-production.yml triggers automatically
```

### What Each Deploy Does

1. **Checkout** the target branch
2. **Build frontend** (npm ci → build → build:widget → build:assessment)
3. **Copy frontend bundles** into backend directory
4. **Build Docker image** (multi-stage, production target)
5. **Security scan** with Trivy
6. **Push to ECR** (tagged `prod-{sha}` or `stg-{sha}`)
7. **Update ECS task definitions** (backend, celery, frontend)
8. **Deploy to ECS** with rolling update (wait for stability, 15 min timeout)
9. **Run smoke tests** (health endpoints, frontend reachability)
10. **Tag release** in git (production only: `deploy-prod-{sha}-{timestamp}`)

---

## GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | IAM access key for ECR/ECS/CloudWatch |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key |

All application secrets (DB password, Paubox key, Twilio tokens, Anthropic key, encryption keys) are in **AWS Secrets Manager**, injected into ECS task definitions at runtime.

---

## Staging Environment

| Resource | Value |
|----------|-------|
| **URL** | https://stg.sleeplessinarizona.com |
| **ECS Services** | sleepreach-stg-backend, stg-frontend, stg-celery |
| **Database** | sleepreach-stg-db (RDS PostgreSQL 16.13, encrypted, 3-day backup) |
| **Redis** | sleepreach-stg-redis (ElastiCache, TLS) |
| **Secrets** | `sleepreach/staging` (Secrets Manager) |

---

## Production Environment

| Resource | Value |
|----------|-------|
| **Dashboard** | https://app.sleeplessinarizona.com |
| **API** | https://api.sleeplessinarizona.com |
| **Widget** | https://api.sleeplessinarizona.com/widget-embed.js |
| **Assessment** | https://api.sleeplessinarizona.com/assessment |
| **ECS Services** | sleepreach-prod-backend, prod-frontend, prod-celery |
| **Database** | sleepreach-prod-db (RDS PostgreSQL 16.13, encrypted, 7-day backup) |
| **Redis** | sleepreach-prod-redis (ElastiCache, TLS) |
| **Secrets** | `sleepreach/production` (Secrets Manager) |

### Widget Embed Code

```html
<script src="https://api.sleeplessinarizona.com/widget-embed.js"></script>
```

### Jotform Webhook URL

```
https://api.sleeplessinarizona.com/api/webhooks/jotform
```

---

## Promote & Rollback

### Promote (Automatic)

The Promote workflow runs automatically when CI passes on `dev`. It can also be triggered manually from the GitHub Actions tab.

### Rollback Production

1. Go to **GitHub Actions → Rollback Production**
2. Click **Run workflow**
3. Choose rollback method:
   - `previous-task-definition` — Roll back to the previous ECS revision
   - `specific-image-tag` — Deploy a specific ECR image (e.g., `prod-18513d3`)
4. Choose services: `both`, `backend-only`, or `celery-only`
5. Type `ROLLBACK` to confirm
6. Post-rollback: automatic health check verification

### Manual Rollback via AWS CLI

```bash
# List recent ECR images
aws ecr describe-images \
  --repository-name sleepreach/backend \
  --query 'imageDetails[?imageTags[?starts_with(@,`prod-`)]].imageTags[]' \
  --output text --profile sleepreach --region us-east-2

# Force redeploy current task definition
aws ecs update-service \
  --cluster sleepreach-cluster \
  --service sleepreach-prod-backend \
  --force-new-deployment \
  --profile sleepreach --region us-east-2
```

---

## Database Migrations

Migrations are applied via the initial schema files:

- `database/init/001_initial_schema.sql` — Leads table, enums, indexes, RLS
- `database/init/002_users_and_providers.sql` — Users, providers, notes, settings

For new migrations, add numbered SQL files and apply via ECS exec or the backup task override pattern.

---

## Health Checks

| Endpoint | Checks | Used By |
|----------|--------|---------|
| `GET /health` | API + Database connectivity | ALB health check |
| `GET /health/ready` | DB + Redis + Queue depths | Deep readiness (CI smoke tests) |
| `GET /health/live` | API process alive | ALB liveness probe |

### Quick Health Check

```bash
# Production
curl https://api.sleeplessinarizona.com/health
curl https://api.sleeplessinarizona.com/health/ready
curl https://api.sleeplessinarizona.com/health/live
```

---

## Monitoring

### CloudWatch Dashboard

**URL:** https://us-east-2.console.aws.amazon.com/cloudwatch/home?region=us-east-2#dashboards/dashboard/SleepReach-Production

### Alarms (12)

| Alarm | Threshold | Notification |
|-------|-----------|-------------|
| Backend CPU High | > 80% for 5 min | SNS → sleepreach-production-alerts |
| Backend Memory High | > 80% for 5 min | SNS → sleepreach-production-alerts |
| ALB 5xx Errors | > 10 in 5 min | SNS → sleepreach-production-alerts |
| RDS CPU High | > 80% for 5 min | SNS → sleepreach-production-alerts |
| ALB Response Time High | P99 > 5s for 15 min (3/3) | SNS → sleepreach-production-alerts |
| ALB Target 5xx High | > 10 in 10 min (2/2) | SNS → sleepreach-production-alerts |
| ALB Unhealthy Hosts | ≥ 1 for 10 min | SNS → sleepreach-production-alerts |
| Celery CPU High | > 80% for 10 min | SNS → sleepreach-production-alerts |
| Celery Memory High | > 80% for 10 min | SNS → sleepreach-production-alerts |
| Service Degraded | Running < Desired for 10 min | SNS → sleepreach-production-alerts |
| RDS Connections High | > 80 for 10 min | SNS → sleepreach-production-alerts |
| RDS Storage Low | < 5GB | SNS → sleepreach-production-alerts |

### Log Groups

| Log Group | Retention |
|-----------|-----------|
| `/ecs/sleepreach-prod-backend` | 30 days |
| `/ecs/sleepreach-prod-frontend` | 30 days |
| `/ecs/sleepreach-prod-celery` | 30 days |
| `/ecs/sleepreach-stg-*` | 30 days |

### View Logs

```bash
# Recent backend logs
aws logs tail /ecs/sleepreach-prod-backend --since 1h \
  --profile sleepreach --region us-east-2

# Follow logs in real time
aws logs tail /ecs/sleepreach-prod-backend --follow \
  --profile sleepreach --region us-east-2
```

---

## Troubleshooting

### ECS Service Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster sleepreach-cluster \
  --services sleepreach-prod-backend \
  --query 'services[0].events[:5]' \
  --profile sleepreach --region us-east-2

# Check task stopped reason
aws ecs list-tasks --cluster sleepreach-cluster --service-name sleepreach-prod-backend \
  --desired-status STOPPED --profile sleepreach --region us-east-2
```

### Health Check Failing

```bash
# Test directly
curl -v https://api.sleeplessinarizona.com/health

# Check ALB target group health
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --profile sleepreach --region us-east-2
```

### Database Connection Issues

```bash
# Verify RDS is available
aws rds describe-db-instances \
  --db-instance-identifier sleepreach-prod-db \
  --query 'DBInstances[0].DBInstanceStatus' \
  --profile sleepreach --region us-east-2
```

### Force Redeploy (Same Image)

```bash
aws ecs update-service \
  --cluster sleepreach-cluster \
  --service sleepreach-prod-backend \
  --force-new-deployment \
  --profile sleepreach --region us-east-2
```

---

## Backup & Recovery

### Automated Backups

| Type | Schedule | Retention | S3 Bucket |
|------|----------|-----------|-----------|
| RDS Automated | Daily 03:00-04:00 UTC | 7 days (prod), 3 days (stg) | — (RDS managed) |
| GitHub Actions Daily | Daily 02:00 UTC | In S3 | sleepreach-backups-prod |
| GitHub Actions Weekly | Sunday 04:00 UTC | In S3 | sleepreach-backups-prod |

### Manual Database Snapshot

```bash
aws rds create-db-snapshot \
  --db-instance-identifier sleepreach-prod-db \
  --db-snapshot-identifier sleepreach-manual-$(date +%Y%m%d) \
  --profile sleepreach --region us-east-2
```

### Restore from Point-in-Time

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier sleepreach-prod-db \
  --target-db-instance-identifier sleepreach-restore-db \
  --restore-time "2026-04-16T12:00:00Z" \
  --profile sleepreach --region us-east-2
```

### Trigger Manual Backup via GitHub Actions

1. Go to **GitHub Actions → Database Backup**
2. Click **Run workflow**
3. Choose `daily` or `weekly`

---

## Cost Estimate (Monthly)

| Service | Cost |
|---------|------|
| ECS Fargate (6 tasks × 0.25 vCPU, 512MB) | ~$40 |
| RDS db.t3.micro × 2 (prod + stg) | ~$30 |
| ElastiCache cache.t3.micro × 2 | ~$24 |
| ALB (shared with NeuroReach) | ~$8 |
| CloudWatch (dashboard + alarms + logs) | ~$5 |
| ECR (container images) | ~$1 |
| **Total** | **~$108/month** |

---

## Contacts

| Role | Name | Email |
|------|------|-------|
| Primary Admin | Evan Mwaniki | emwaniki@tmsinstitute.co |
| Administrator | Ruchir Patel | rpatel@sleeplessinarizona.com |
| Administrator | Rachel Patel | rlpatel@sleeplessinarizona.com |
