# SleepReach — Complete CI/CD Pipeline Implementation Plan

> **Purpose:** Step-by-step tasks for a new Cline session to clean up, verify, and fully operationalize the SleepReach deployment pipeline.  
> **Repo:** `https://github.com/EvanMaina/SleepReach.git`  
> **Clone:** `c:\Users\hp\SleepReach-Clean`  
> **AWS Account:** 131880217305 (us-east-2)  
> **Date prepared:** 2026-04-21

---

## Table of Contents

1. [Context & Current State](#1-context--current-state)
2. [Pre-requisites](#2-pre-requisites)
3. [Task List (Ordered)](#3-task-list-ordered)
4. [Pipeline Architecture](#4-pipeline-architecture)
5. [Detailed Task Descriptions](#5-detailed-task-descriptions)
6. [Database Migration Strategy](#6-database-migration-strategy)
7. [Backup & Restore Procedures](#7-backup--restore-procedures)
8. [Rollback Procedures](#8-rollback-procedures)
9. [Monitoring & Alerts](#9-monitoring--alerts)
10. [Version Upgrade Strategy](#10-version-upgrade-strategy)
11. [Local Development Workflow](#11-local-development-workflow)

---

## 1. Context & Current State

### What exists and works

| Component | Status | Details |
|-----------|--------|---------|
| **GitHub Repo** | ✅ Correct | `EvanMaina/SleepReach` — branches `dev`, `stg`, `main` all at `c24c8a2` |
| **AWS ECS Cluster** | ✅ Running | `sleepreach-cluster` with 6 services (3 staging + 3 production) |
| **Production services** | ✅ Healthy | backend `:34`, frontend `:31`, celery `:34` — all running `c24c8a2` |
| **Staging services** | ✅ Healthy | backend `:25`, frontend `:23`, celery `:26` — all running `c24c8a2` |
| **RDS PostgreSQL** | ✅ Available | `sleepreach-prod-db` (prod) + `sleepreach-stg-db` (staging) |
| **ElastiCache Redis** | ✅ Available | `sleepreach-prod-redis-tls` + `sleepreach-stg-redis-tls` |
| **ECR Repos** | ✅ Exist | `sleepreach/backend` + `sleepreach/frontend` |
| **S3 Backups** | ✅ Bucket exists | `sleepreach-backups-prod` |
| **CI/CD Workflows** | ✅ 6 files | `ci.yml`, `promote.yml`, `deploy-staging.yml`, `deploy-production.yml`, `rollback.yml`, `backup.yml` |
| **Live URLs** | ✅ Working | `app.sleeplessinarizona.com` (frontend), `api.sleeplessinarizona.com` (backend) |

### What needs cleanup / improvement

| Issue | Impact | Fix |
|-------|--------|-----|
| **Old local repo pointed to NeuroReachAI remote** | Confusion, risk of cross-contamination | Fresh clone done at `c:\Users\hp\SleepReach-Clean` ✅ |
| **Pipeline auto-promotes dev→stg→main→prod in one shot** | No staging gate check before production | Refactor to: push stg → deploy staging, merge to main → deploy production |
| **No Alembic migration step in deploy** | Schema changes need manual intervention | Add migration step to deploy workflows |
| **Backup cron may not be running** | No verified recent backups | Verify and test backup workflow |
| **No CloudWatch alarms/dashboard** | Blind to 5xx, latency, task failures | Create dashboard + alarms |
| **No branch protection rules** | Anyone can push directly to main/stg | Add GitHub branch protection |
| **Frontend cross-contamination still possible** | Wrong images could be deployed | Repo identity guard already exists, but verify it works |

---

## 2. Pre-requisites

Before starting the tasks, ensure you have:

1. **AWS credentials** (temporary session token for account `131880217305`)
2. **GitHub access** to `EvanMaina/SleepReach` (push access to all branches)
3. **GitHub Secrets** already configured in the repo:
   - `AWS_ACCESS_KEY_ID` — IAM access key for CI/CD (NOT session tokens)
   - `AWS_SECRET_ACCESS_KEY` — IAM secret key
4. **Local tools:** `git`, `docker`, `aws` CLI, `node` v22, `python` 3.11, `pip`
5. **The fresh clone** at `c:\Users\hp\SleepReach-Clean` (already done)

### GitHub Secrets to verify

```bash
gh secret list --repo EvanMaina/SleepReach
```

Required secrets:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

---

## 3. Task List (Ordered)

> **Copy this as your task_progress checklist in the new session.**

```
- [ ] TASK 1: Verify repo state and switch to dev branch
- [ ] TASK 2: Refactor CI/CD pipeline (separate staging and production triggers)
- [ ] TASK 3: Add Alembic database migration step to deploy workflows
- [ ] TASK 4: Add GitHub branch protection rules
- [ ] TASK 5: Verify and test backup workflow
- [ ] TASK 6: Create CloudWatch dashboard and alarms
- [ ] TASK 7: Verify GitHub Secrets and IAM permissions
- [ ] TASK 8: Test the full pipeline (dev → staging → production)
- [ ] TASK 9: Create operations runbook update
- [ ] TASK 10: Final verification and sign-off
```

---

## 4. Pipeline Architecture

### Current (auto-promote everything)

```
push to dev → CI → merge dev→stg → deploy staging → merge stg→main → deploy production
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                    ALL AUTOMATIC — one push deploys everywhere
```

### Target (controlled promotion)

```
Developer Workflow:
  1. Work locally on dev branch
  2. Push to dev → CI runs (lint + test)
  3. Merge dev → stg (PR or manual) → deploys to STAGING automatically
  4. Test on staging
  5. Merge stg → main (PR) → deploys to PRODUCTION automatically
  
Triggers:
  push/merge to stg  →  deploy-staging.yml  →  builds + deploys to staging ECS
  push/merge to main →  deploy-production.yml → builds + deploys to production ECS
  
Safety:
  - Branch protection: main requires PR + review
  - Repo identity guard prevents cross-contamination
  - Post-deploy smoke tests verify health
  - Rollback workflow available for emergencies
```

### Workflow file changes needed

| File | Change |
|------|--------|
| `promote.yml` | **DELETE or DISABLE** — no longer auto-promote |
| `deploy-staging.yml` | Already triggers on `push to stg` ✅ — just verify |
| `deploy-production.yml` | Already triggers on `push to main` ✅ — just verify, remove `workflow_call` dependency on `ci` if CI runs separately |
| `ci.yml` | Expand to run on PRs to `stg` and `main` too |
| `rollback.yml` | Keep as-is ✅ |
| `backup.yml` | Keep as-is ✅ — verify it runs |

---

## 5. Detailed Task Descriptions

### TASK 1: Verify repo state and switch to dev branch

```bash
# From the clean clone
git -C "c:\Users\hp\SleepReach-Clean" remote -v
# Should show: origin https://github.com/EvanMaina/SleepReach.git

git -C "c:\Users\hp\SleepReach-Clean" branch -v
# Should show dev, stg, main all at c24c8a2

git -C "c:\Users\hp\SleepReach-Clean" checkout dev
```

**Verify AWS connectivity:**
```bash
aws ecs describe-services --profile <PROFILE> --cluster sleepreach-cluster \
  --services sleepreach-prod-backend --query "services[0].status" --region us-east-2
```

---

### TASK 2: Refactor CI/CD pipeline

**Goal:** Push/merge to `stg` deploys staging. Push/merge to `main` deploys production. No auto-promote.

#### 2a. Disable promote.yml

Rename or remove the promote workflow. The simplest approach:

```yaml
# .github/workflows/promote.yml
# DISABLED — replaced by direct branch-triggered deploys
# See deploy-staging.yml (triggers on push to stg)
# See deploy-production.yml (triggers on push to main)
name: "[DISABLED] Promote"
on:
  workflow_dispatch:
    inputs:
      note:
        description: "This workflow is disabled. Use branch merges instead."
        required: false
```

#### 2b. Update ci.yml

Ensure CI runs on:
- Push to `dev`
- PRs to `stg` and `main`

```yaml
on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev, stg, main]
```

#### 2c. Verify deploy-staging.yml triggers

Already has:
```yaml
on:
  push:
    branches: [stg]
  workflow_dispatch:
  workflow_call:
```

The `push to stg` trigger is correct. When you merge `dev → stg` (via PR or direct push), it will auto-deploy to staging. **Keep `workflow_call` for backward compatibility but it won't be used by promote anymore.**

#### 2d. Verify deploy-production.yml triggers

Already has:
```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
  workflow_call:
```

The `push to main` trigger is correct. When you merge `stg → main` (via PR), it will auto-deploy to production.

**Important:** The current production deploy has a `ci` job that runs before build-and-deploy:
```yaml
ci:
  if: ${{ !(inputs.skip_ci || false) }}
  uses: ./.github/workflows/ci.yml
```

This is fine — when triggered by `push to main`, CI runs first. When called from promote with `skip_ci: true`, it skips. Since we're removing promote, the CI step will always run on push to main, which is good.

#### 2e. Summary of file changes

| File | Action |
|------|--------|
| `promote.yml` | Gut the contents, replace with disabled stub |
| `ci.yml` | Add `pull_request: branches: [stg, main]` if not already there |
| `deploy-staging.yml` | No changes needed |
| `deploy-production.yml` | No changes needed |

---

### TASK 3: Add Alembic database migration step

**Goal:** Run `alembic upgrade head` as part of every deploy before the new code starts serving traffic.

#### Check if Alembic is already configured

```bash
# In the clean clone
dir backend\alembic 2>nul
dir backend\alembic.ini 2>nul
dir backend\migrations 2>nul
```

#### If Alembic is NOT configured, set it up:

1. Add to `backend/requirements.txt`: `alembic>=1.13`
2. Initialize: `cd backend && alembic init migrations`
3. Configure `alembic.ini` to use `DATABASE_URL` env var
4. Create initial migration from existing models
5. **CRITICAL: Use `--autogenerate` but mark as "baseline" — do NOT run against production since tables already exist**

#### Add migration step to deploy workflows

Add this step AFTER AWS auth and BEFORE deploying the new task definition:

```yaml
- name: Run database migrations
  run: |
    # Run migrations via ECS run-task with the NEW image
    aws ecs run-task \
      --cluster ${{ env.ECS_CLUSTER }} \
      --task-definition <NEWLY-REGISTERED-TD> \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={...}" \
      --overrides '{
        "containerOverrides": [{
          "name": "backend",
          "command": ["alembic", "upgrade", "head"]
        }]
      }'
    # Wait for task to complete
    aws ecs wait tasks-stopped --cluster ${{ env.ECS_CLUSTER }} --tasks $TASK_ARN
```

**Alternative (simpler):** If the app already runs migrations on startup (e.g., `CREATE TABLE IF NOT EXISTS`), this step may not be needed. Check `backend/src/main.py` for auto-migration logic.

---

### TASK 4: Add GitHub branch protection rules

```bash
# Protect main branch — require PR, no direct push
gh api repos/EvanMaina/SleepReach/branches/main/protection \
  --method PUT \
  --field required_pull_request_reviews='{"required_approving_review_count":0}' \
  --field enforce_admins=false \
  --field required_status_checks=null \
  --field restrictions=null

# Protect stg branch — allow merges from dev only via PR or direct push
# (lighter protection since it's staging)
```

**Note:** If using GitHub Free (not Pro/Team), branch protection rules are limited. Check the plan:
```bash
gh api repos/EvanMaina/SleepReach --jq '.private, .owner.type'
```

---

### TASK 5: Verify and test backup workflow

1. **Check last backup run:**
```bash
gh run list --workflow backup.yml --repo EvanMaina/SleepReach --limit 5
```

2. **Check S3 for actual backup files:**
```bash
aws s3 ls s3://sleepreach-backups-prod/ --recursive --profile <PROFILE> --region us-east-2
```

3. **Trigger a manual backup:**
```bash
gh workflow run backup.yml --repo EvanMaina/SleepReach -f backup_type=daily
```

4. **Verify the backup file was created in S3**

5. **Test restore (on staging, never production):**
```bash
# Download backup
aws s3 cp s3://sleepreach-backups-prod/rds/daily/<date>/sleepreach_<timestamp>.sql.gz /tmp/

# Restore to staging DB (via ECS run-task or bastion)
gunzip /tmp/sleepreach_*.sql.gz
psql -h <staging-rds-endpoint> -U <user> -d sleepreach_staging < /tmp/sleepreach_*.sql
```

---

### TASK 6: Create CloudWatch dashboard and alarms

#### Dashboard

Create `infrastructure/cloudwatch-dashboard.json` (may already exist — check and update):

Key metrics to include:
- ECS service CPU/Memory utilization (all 6 services)
- ALB request count, 5xx rate, response time (p99)
- RDS CPU, connections, free storage, read/write latency
- Redis CPU, memory, cache hit rate
- Celery queue depths (from custom metrics or Redis keys)

#### Alarms

| Alarm | Metric | Threshold | Action |
|-------|--------|-----------|--------|
| Prod 5xx spike | ALB 5xx count | > 10 in 5 min | SNS notification |
| Prod p99 latency | ALB target response time | > 5s for 5 min | SNS notification |
| Backend task failure | ECS running task count | < 1 for 2 min | SNS notification |
| RDS CPU | CPU utilization | > 80% for 10 min | SNS notification |
| RDS free storage | Free storage space | < 1 GB | SNS notification |
| Redis memory | Used memory | > 80% max | SNS notification |

**Create via AWS CLI or CloudFormation/Terraform:**

```bash
# Example: ALB 5xx alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "sleepreach-prod-5xx-high" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=LoadBalancer,Value=<ALB-ARN-SUFFIX> \
  --alarm-actions <SNS-TOPIC-ARN> \
  --region us-east-2
```

---

### TASK 7: Verify GitHub Secrets and IAM permissions

```bash
# List secrets
gh secret list --repo EvanMaina/SleepReach

# Required secrets:
# AWS_ACCESS_KEY_ID       — IAM user access key (NOT session token)
# AWS_SECRET_ACCESS_KEY   — IAM user secret key
```

**If using session tokens:** GitHub Actions needs long-lived IAM credentials (access key + secret). Session tokens expire. Create a dedicated IAM user:

```bash
aws iam create-user --user-name github-actions-sleepreach
aws iam attach-user-policy --user-name github-actions-sleepreach \
  --policy-arn arn:aws:iam::131880217305:policy/SleepReachCICD
aws iam create-access-key --user-name github-actions-sleepreach
```

**Required IAM permissions:**
- `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, etc.
- `ecs:DescribeServices`, `ecs:DescribeTaskDefinition`, `ecs:RegisterTaskDefinition`, `ecs:UpdateService`, `ecs:RunTask`
- `s3:PutObject` (for backups)
- `logs:GetLogEvents` (for debugging)

---

### TASK 8: Test the full pipeline

#### 8a. Test staging deploy

```bash
# On dev branch, make a small change
git checkout dev
echo "# Test change $(date)" >> README.md
git add README.md
git commit -m "test: verify staging pipeline"
git push origin dev

# Merge to stg
git checkout stg
git merge dev
git push origin stg
# → This should trigger deploy-staging.yml
# → Monitor: gh run watch --repo EvanMaina/SleepReach
```

#### 8b. Verify staging

```bash
curl -sf https://api.sleeplessinarizona.com/health  # or staging URL
```

#### 8c. Test production deploy

```bash
# Create PR from stg to main
gh pr create --base main --head stg --title "Deploy to production" --body "Staging verified"

# Merge the PR
gh pr merge <PR-NUMBER> --merge

# → This should trigger deploy-production.yml
# → Monitor: gh run watch --repo EvanMaina/SleepReach
```

#### 8d. Verify production

```bash
curl -sf https://api.sleeplessinarizona.com/health
curl -sf https://app.sleeplessinarizona.com
```

---

### TASK 9: Update operations runbook

Update `docs/OPERATIONS_RUNBOOK.md` with:
- New pipeline flow (no more auto-promote)
- How to deploy to staging (merge to stg)
- How to deploy to production (PR from stg to main)
- How to rollback (GitHub Actions UI → rollback.yml)
- How to run manual backup
- How to restore from backup
- CloudWatch dashboard URL
- Alarm escalation procedures

---

### TASK 10: Final verification and sign-off

- [ ] All 6 ECS services running and healthy
- [ ] `deploy-staging.yml` triggers on push to `stg`
- [ ] `deploy-production.yml` triggers on push to `main`
- [ ] `promote.yml` is disabled
- [ ] Branch protection on `main`
- [ ] Backup workflow runs successfully
- [ ] CloudWatch dashboard shows metrics
- [ ] Alarms configured and tested
- [ ] Production data preserved (verify lead count matches)
- [ ] Rollback workflow tested (or at least verified inputs)
- [ ] Documentation updated

---

## 6. Database Migration Strategy

### Preserving existing production data

**CRITICAL:** The production database (`sleepreach-prod-db`) has live data (leads, providers, users). All deployments must:

1. **Never run `DROP TABLE` or destructive DDL** in migrations
2. **Use Alembic migrations** with `--autogenerate` to detect schema changes
3. **Test migrations on staging first** (staging DB mirrors production schema)
4. **Take a backup before any migration** (backup workflow or manual `pg_dump`)

### Migration workflow

```
1. Developer adds/changes models in backend/src/models/
2. Generate migration: alembic revision --autogenerate -m "description"
3. Review generated migration file — remove any DROP statements
4. Commit migration to dev branch
5. Push to dev → CI runs
6. Merge to stg → deploy-staging runs migrations on staging DB
7. Verify staging works correctly
8. Merge to main → deploy-production runs migrations on production DB
```

### Baseline migration (first time)

Since the production database already has tables, you need to create a **baseline migration** that marks the current state as "done" without actually running any SQL:

```bash
alembic revision --autogenerate -m "baseline: existing schema"
# Then mark it as applied without running:
alembic stamp head  # Run against production to mark current state
```

---

## 7. Backup & Restore Procedures

### Automated backups (already configured)

| Type | Schedule | Retention |
|------|----------|-----------|
| Daily | 02:00 UTC (Mon-Sat) | Keep last 7 |
| Weekly | 04:00 UTC (Sunday) | Keep last 4 |

**Workflow:** `.github/workflows/backup.yml` → runs ECS Fargate task → `pg_dump` → upload to `s3://sleepreach-backups-prod/`

### Manual backup

```bash
# Trigger via GitHub Actions
gh workflow run backup.yml --repo EvanMaina/SleepReach -f backup_type=daily

# Or via AWS CLI (direct ECS run-task)
aws ecs run-task --cluster sleepreach-cluster \
  --task-definition sleepreach-prod-backend:34 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={...}" \
  --overrides '{"containerOverrides":[{"name":"backend","command":["python","scripts/backup_database.py","--type","manual"]}]}'
```

### Restore procedure

```bash
# 1. Download backup from S3
aws s3 cp s3://sleepreach-backups-prod/rds/daily/2026/04/21/sleepreach_*.sql.gz ./backup.sql.gz

# 2. Decompress
gunzip backup.sql.gz

# 3. Restore to target database
psql -h <rds-endpoint> -U <username> -d <database> < backup.sql

# 4. Verify
psql -h <rds-endpoint> -U <username> -d <database> -c "SELECT count(*) FROM leads;"
```

### RDS automated snapshots

In addition to `pg_dump` backups, AWS RDS has automated snapshots:
```bash
aws rds describe-db-snapshots --db-instance-identifier sleepreach-prod-db \
  --query "DBSnapshots[*].{id:DBSnapshotIdentifier,time:SnapshotCreateTime}" --output table
```

---

## 8. Rollback Procedures

### Option 1: GitHub Actions rollback workflow (recommended)

1. Go to GitHub Actions → "🔄 Rollback Production"
2. Click "Run workflow"
3. Choose method:
   - `previous-task-definition` — reverts to the task def revision before the current one
   - `specific-image-tag` — specify an ECR tag like `prod-c24c8a2`
4. Choose scope: `both`, `backend-only`, or `celery-only`
5. Type `ROLLBACK` to confirm

### Option 2: AWS CLI manual rollback

```bash
# Get current task definition
aws ecs describe-services --cluster sleepreach-cluster \
  --services sleepreach-prod-backend \
  --query 'services[0].taskDefinition' --output text
# → arn:aws:ecs:us-east-2:131880217305:task-definition/sleepreach-prod-backend:34

# Rollback to previous revision
aws ecs update-service --cluster sleepreach-cluster \
  --service sleepreach-prod-backend \
  --task-definition sleepreach-prod-backend:33 \
  --force-new-deployment

# Wait for stability
aws ecs wait services-stable --cluster sleepreach-cluster \
  --services sleepreach-prod-backend
```

### Option 3: Git revert + redeploy

```bash
# On main branch, revert the bad commit
git checkout main
git revert HEAD
git push origin main
# → deploy-production.yml triggers automatically
```

---

## 9. Monitoring & Alerts

### Health endpoints

| Endpoint | Purpose |
|----------|---------|
| `/health` | Full health check (DB + Redis + queues) |
| `/health/live` | Liveness probe (is the process running?) |
| `/health/ready` | Readiness probe (can it serve traffic?) |
| `/health/notifications` | Paubox, Twilio, Celery broker connectivity |

### CloudWatch Log Groups

```
/ecs/sleepreach-prod-backend
/ecs/sleepreach-prod-frontend
/ecs/sleepreach-prod-celery
/ecs/sleepreach-stg-backend
/ecs/sleepreach-stg-frontend
/ecs/sleepreach-stg-celery
```

### Key metrics to watch

- **ECS:** Running task count, CPU/memory utilization
- **ALB:** Request count, 5xx/4xx rate, response time percentiles
- **RDS:** CPU, connections, free storage, replication lag
- **Redis:** Memory usage, connections, cache hit rate
- **Celery:** Queue depth (via `/health/ready` endpoint)

---

## 10. Version Upgrade Strategy

### Application version upgrades

1. Make changes on `dev` branch
2. Update version in `backend/src/main.py` (if versioned)
3. Update `CHANGELOG.md`
4. Push to `dev` → CI validates
5. Merge to `stg` → deploys to staging
6. Verify on staging
7. Merge to `main` → deploys to production

### Python version upgrade (e.g., 3.11 → 3.12)

1. Update `backend/Dockerfile` base image
2. Update `ci.yml` Python version
3. Update `deploy-staging.yml` and `deploy-production.yml` Python version
4. Test locally with new Python version
5. Deploy to staging first, verify
6. Deploy to production

### Node.js version upgrade (e.g., 22 → 24)

1. Update `frontend/Dockerfile` base image
2. Update workflow files Node version
3. Run `npm ci && npm run build` locally to verify
4. Deploy to staging, verify
5. Deploy to production

### PostgreSQL version upgrade

1. **Take a full backup first** (manual + automated)
2. Create a new RDS instance with the target version
3. Use `pg_dump`/`pg_restore` to migrate data
4. Update application environment variables to point to new DB
5. Test on staging first
6. Schedule a maintenance window for production
7. Use RDS Blue/Green deployment if available:
```bash
aws rds create-blue-green-deployment \
  --blue-green-deployment-name sleepreach-pg-upgrade \
  --source arn:aws:rds:us-east-2:131880217305:db:sleepreach-prod-db \
  --target-engine-version "16.4"
```

### Docker base image updates

1. Periodically update base images in Dockerfiles
2. Run Trivy security scan (already in CI/CD)
3. Test on staging
4. Deploy to production

---

## 11. Local Development Workflow

### Initial setup

```bash
# 1. Clone the repo
git clone https://github.com/EvanMaina/SleepReach.git
cd SleepReach

# 2. Checkout dev branch
git checkout dev

# 3. Copy environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 4. Edit .env files with local/dev credentials

# 5. Start local services
docker-compose up -d

# 6. Install frontend dependencies (for local dev server)
cd frontend && npm install && cd ..

# 7. Run backend locally
cd backend && pip install -r requirements.txt
python -m uvicorn src.main:app --reload --port 8000

# 8. Run frontend dev server
cd frontend && npm run dev
```

### Development → Deployment flow

```
┌─────────────────────────────────────────────────────────┐
│  LOCAL (dev branch)                                      │
│  1. Code changes                                        │
│  2. Test locally: docker-compose up                     │
│  3. git add + commit + push origin dev                  │
│  4. CI runs automatically                               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  STAGING (stg branch)                                    │
│  5. Create PR: dev → stg (or direct merge)              │
│  6. Merge PR → push to stg triggers deploy-staging.yml  │
│  7. Verify on staging URL                               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  PRODUCTION (main branch)                                │
│  8. Create PR: stg → main                               │
│  9. Merge PR → push to main triggers deploy-production  │
│  10. Verify on production URL                           │
│  11. Auto-tagged: deploy-prod-<sha>-<timestamp>         │
└─────────────────────────────────────────────────────────┘
```

### Useful commands

```bash
# Check CI status
gh run list --repo EvanMaina/SleepReach

# Watch a running workflow
gh run watch --repo EvanMaina/SleepReach

# Trigger manual staging deploy
gh workflow run "Deploy to Staging" --repo EvanMaina/SleepReach

# Trigger manual production deploy
gh workflow run "Deploy to Production" --repo EvanMaina/SleepReach

# Trigger manual backup
gh workflow run backup.yml --repo EvanMaina/SleepReach -f backup_type=daily

# Trigger rollback
gh workflow run rollback.yml --repo EvanMaina/SleepReach

# Check production health
curl -sf https://api.sleeplessinarizona.com/health | python -m json.tool

# View production logs
aws logs tail /ecs/sleepreach-prod-backend --follow --region us-east-2
```

---

## Quick Reference Card

| What | How |
|------|-----|
| Deploy to staging | Merge `dev → stg` |
| Deploy to production | Merge `stg → main` |
| Rollback production | GitHub Actions → "Rollback Production" |
| Run backup | GitHub Actions → "Database Backup" |
| Check health | `curl https://api.sleeplessinarizona.com/health` |
| View logs | `aws logs tail /ecs/sleepreach-prod-backend --follow` |
| Run CI manually | `gh workflow run ci.yml --repo EvanMaina/SleepReach` |

---

*Provide this file along with `DEPLOYMENT_STATUS.md` at the start of a new Cline session. Supply fresh AWS credentials when prompted.*
