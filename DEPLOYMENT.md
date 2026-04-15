# SleepReach — AWS Deployment Architecture

## Overview

SleepReach is deployed on AWS ECS Fargate in the `us-east-2` (Ohio) region, sharing the VPC and ALB with NeuroReach AI for cost optimization.

## Architecture Diagram

```
                    ┌──────────────────────────┐
                    │   sleeplessinarizona.com  │
                    │   (DNS managed by IT)     │
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │   AWS ACM Certificate    │
                    │   *.sleeplessinarizona.com│
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │   Application Load       │
                    │   Balancer (shared)       │
                    │   neuroreach-ai-alb       │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
    │ app.sleep...  │  │ api.sleep...│  │ stg.sleep...│
    │ → Frontend    │  │ → Backend   │  │ → Staging   │
    └───────────────┘  └─────────────┘  └─────────────┘
              │                │                │
    ┌─────────▼────────────────▼────────────────▼─────────┐
    │              ECS Cluster: sleepreach-cluster          │
    │                                                       │
    │  Production:                  Staging:                │
    │  ├─ sleepreach-prod-backend   ├─ sleepreach-stg-backend│
    │  ├─ sleepreach-prod-frontend  ├─ sleepreach-stg-frontend│
    │  └─ sleepreach-prod-celery    └─ sleepreach-stg-celery │
    └──────────────────────┬────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
    │ RDS      │    │ ElastiCache │   │ Secrets     │
    │ PostgreSQL│    │ Redis       │   │ Manager     │
    └──────────┘    └─────────────┘   └─────────────┘
```

## AWS Resources

### Compute (ECS Fargate)
| Service | CPU | Memory | Environment |
|---------|-----|--------|-------------|
| sleepreach-prod-backend | 256 | 512MB | production |
| sleepreach-prod-frontend | 256 | 512MB | production |
| sleepreach-prod-celery | 256 | 512MB | production |
| sleepreach-stg-backend | 256 | 512MB | staging |
| sleepreach-stg-frontend | 256 | 512MB | staging |
| sleepreach-stg-celery | 256 | 512MB | staging |

### Database (RDS PostgreSQL 14)
| Instance | Type | Storage | Backup | Encrypted |
|----------|------|---------|--------|-----------|
| sleepreach-prod-db | db.t3.micro | 20GB gp3 | 7 days | Yes |
| sleepreach-stg-db | db.t3.micro | 20GB gp3 | 3 days | Yes |

**Endpoint (prod):** `sleepreach-prod-db.cfggkciq6tun.us-east-2.rds.amazonaws.com:5432`
**Endpoint (stg):** `sleepreach-stg-db.cfggkciq6tun.us-east-2.rds.amazonaws.com:5432`

### Cache (ElastiCache Redis 7.1)
| Instance | Type | Environment |
|----------|------|-------------|
| sleepreach-prod-redis | cache.t3.micro | production |
| sleepreach-stg-redis | cache.t3.micro | staging |

### Networking
- **VPC:** vpc-00bed95435b092a79 (shared with NeuroReach, 10.0.0.0/16)
- **ALB:** neuroreach-ai-alb (shared, HTTPS on port 443)
- **Security Groups:**
  - `sg-0edebbac3eb66c47a` — ECS tasks
  - `sg-08abf0d99874ca3cb` — RDS database
  - `sg-0def53df8f192c482` — Redis cache

### Container Registry (ECR)
- `131880217305.dkr.ecr.us-east-2.amazonaws.com/sleepreach/backend`
- `131880217305.dkr.ecr.us-east-2.amazonaws.com/sleepreach/frontend`

### Monitoring
- **Health Dashboard:** https://us-east-2.console.aws.amazon.com/cloudwatch/home?region=us-east-2#dashboards/dashboard/SleepReach-Production
- **Log Groups:** `/ecs/sleepreach-prod-*` and `/ecs/sleepreach-stg-*` (30-day retention)

### Secrets
- `sleepreach/production` — Production credentials (Secrets Manager)
- `sleepreach/staging` — Staging credentials (Secrets Manager)

## URLs

### Production
| URL | Purpose |
|-----|---------|
| `https://app.sleeplessinarizona.com` | Coordinator Dashboard |
| `https://api.sleeplessinarizona.com` | Backend API |
| `https://api.sleeplessinarizona.com/widget-embed.js` | **Widget embed script** |
| `https://api.sleeplessinarizona.com/assessment` | Assessment form |

### Staging
| URL | Purpose |
|-----|---------|
| `https://stg.sleeplessinarizona.com` | Staging Dashboard |

### Widget Embed Code (for website)
```html
<script src="https://api.sleeplessinarizona.com/widget-embed.js"></script>
```

### Jotform Webhook URL
```
https://api.sleeplessinarizona.com/api/webhooks/jotform
```

## Deployment Flow

```
dev (local) → stg (staging) → main (production)
```

### How to deploy:
1. **Develop locally** on `dev` branch
2. **Push to staging:** `git checkout stg && git merge dev && git push`
   - GitHub Actions runs: TypeScript check → Vite build → Docker build → Push to ECR → Update ECS
3. **Test on staging:** Visit `https://stg.sleeplessinarizona.com`
4. **Deploy to production:** `git checkout main && git merge stg && git push`
   - Same CI/CD pipeline → Production ECS updated

### CI/CD Checks (runs before every deployment):
1. TypeScript compilation (`tsc --noEmit`)
2. Vite production build (catches import/build errors)
3. Docker image build (validates Dockerfiles)
4. ECS service health check (waits for healthy containers)

## Backup Strategy

### Database Backups
- **Production:** Automated daily backups, 7-day retention
  - Backup window: 03:00-04:00 UTC
  - Point-in-time recovery enabled
- **Staging:** Automated daily backups, 3-day retention

### Manual Snapshot
```bash
aws rds create-db-snapshot \
  --db-instance-identifier sleepreach-prod-db \
  --db-snapshot-identifier sleepreach-manual-$(date +%Y%m%d)
```

### Restore from Backup
```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier sleepreach-prod-db \
  --target-db-instance-identifier sleepreach-restore-db \
  --restore-time "2026-04-15T12:00:00Z"
```

## Environment Separation

| Setting | Local Dev | Staging | Production |
|---------|-----------|---------|------------|
| ENVIRONMENT | development | staging | production |
| Database | Local Docker | RDS (stg) | RDS (prod) |
| Redis | Local Docker | ElastiCache (stg) | ElastiCache (prod) |
| Email | MailDev (fake) | Paubox (real) | Paubox (real) |
| SMS | smsdev (fake) | Twilio (real) | Twilio (real) |
| API Docs | Enabled | Enabled | Disabled |

**Your local dev environment (`backend/.env`) never changes. Production credentials live only in AWS Secrets Manager.**

## Cost Estimate (Monthly)

| Service | Cost |
|---------|------|
| ECS Fargate (6 tasks) | ~$40 |
| RDS db.t3.micro × 2 | ~$30 |
| ElastiCache cache.t3.micro × 2 | ~$24 |
| ALB (shared) | ~$8 |
| CloudWatch | ~$5 |
| ECR | ~$1 |
| **Total** | **~$108/month** |

## Contacts

| Role | Name | Email |
|------|------|-------|
| Primary Admin | Evan Mwaniki | emwaniki@tmsinstitute.co |
| Administrator | Ruchir Patel | rpatel@sleeplessinarizona.com |
| Administrator | Rachel Patel | rlpatel@sleeplessinarizona.com |
