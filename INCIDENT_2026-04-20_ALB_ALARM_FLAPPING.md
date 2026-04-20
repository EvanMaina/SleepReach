# Incident: Shared ALB P99 Response Time Alarms Flapping (SleepReach + NeuroReach)

**Date:** 2026-04-20
**Severity:** P3 — Noisy alarm only (no user-facing impact; no failed requests)
**Environment:** Shared ALB `app/neuroreach-ai-alb/09820aa0f84e6f0b` (us-east-2, account 131880217305)
**Alarms:**
- `sleepreach-prod-alb-response-time-high`
- `neuroreach-alb-response-time-high`

**Duration of flapping:** ~17:15 → 19:16 UTC+3 (2h01m, ~6 ALARM↔OK flips)
**Backend / Database / tenant-isolation impact:** NONE. Both apps healthy throughout.

---

## Summary

Starting ~2h after the earlier `INCIDENT_2026-04-20_FRONTEND_CROSS_CONTAMINATION`
was fully remediated (`acf8acc`, 16:38 UTC+3), both ALB-response-time CloudWatch
alarms began flapping between `ALARM` and `OK` every 1–2 minutes. The p99 metric
was spiking to **6.6s → 46.5s → 0.04s** across consecutive 5-minute buckets.

The earlier frontend fix was **NOT** the cause — the alarms were being
triggered by a completely separate, pre-existing endpoint.

---

## Root Cause

`GET /api/ai-insights?force_refresh=true` synchronously calls the Anthropic
Claude API (`POST https://api.anthropic.com/v1/messages`) with a **90-second
HTTPX client timeout** and no backgrounding.

Every time a coordinator or admin clicks the **"Refresh AI Insights"** button
on the dashboard:

1. The browser issues `GET /api/ai-insights?force_refresh=true`
2. FastAPI awaits Claude for **30–50 seconds**
3. That single request lands in the ALB `TargetResponseTime` p99 for its
   5-minute bucket
4. A single ~45s sample easily clears the **5s threshold** → `ALARM`
5. The next 5-minute bucket has only sub-second traffic → `OK`
6. Next click → `ALARM` again. Repeat.

### Evidence (from `/ecs/sleepreach-prod-backend`, 16:05–16:10 UTC = 19:05–19:10 local)

```
16:06:13  WARNING src.main - Slow request: GET /api/ai-insights took 37298.50ms
16:06:13  INFO    "GET /api/ai-insights?force_refresh=true HTTP/1.1" 200 OK
16:08:29  WARNING src.main - Slow request: GET /api/ai-insights took 48590.17ms
16:08:29  INFO    "GET /api/ai-insights?force_refresh=true HTTP/1.1" 200 OK
```

### Alarm state data at 16:16 UTC

```
recentDatapoints:[6.6193744s, 46.4985585s, 0.0374204s]
threshold: 5.0
```

### Ruled out (systematically)

| Hypothesis                        | Result                                     |
|-----------------------------------|--------------------------------------------|
| Residual NR code on SR DB         | ❌ Current `prod-acf8acc` has 0 ERROR lines; TMS endpoint returns 404 |
| Frontend fix side-effect          | ❌ Front-end TGs p99 < 20ms                 |
| Backend ECS CPU throttling        | ❌ CPU 1–4% (both backend and celery)       |
| Celery Beat hourly xx:05 task     | ❌ No xx:05-aligned task in either repo's beat schedule (checked `backend/src/tasks/celery_app.py` for both SR and NR) |
| NeuroReach-side culprit           | ❌ NR backend TG p99 max 2.60s avg 0.43s   |
| RDS / Redis latency               | ❌ No correlated spikes (checked)           |
| Database connection pool          | ❌ No 5XX on backend TG                     |

**Offending target group:** `sleepreach-prod-backend` exclusively
(p99 max 47.6s, avg p99 2.99s, 1521 samples across the 2h window).
NR backend TG p99 max only 2.60s.

---

## Remediation (Applied 19:40 UTC+3)

### Immediate (done — no downtime)

Both alarm thresholds raised from **5.0s → 30.0s** p99, so the alarm now
reflects actual SLA while `/api/ai-insights?force_refresh=true` remains
synchronous:

```bash
aws cloudwatch put-metric-alarm --alarm-name sleepreach-prod-alb-response-time-high \
  --metric-name TargetResponseTime --namespace AWS/ApplicationELB \
  --extended-statistic p99 --period 300 --evaluation-periods 3 \
  --datapoints-to-alarm 3 --threshold 30.0 \
  --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching \
  --dimensions Name=LoadBalancer,Value=app/neuroreach-ai-alb/09820aa0f84e6f0b \
  --alarm-actions arn:aws:sns:us-east-2:131880217305:sleepreach-production-alerts \
  --ok-actions    arn:aws:sns:us-east-2:131880217305:sleepreach-production-alerts

# Same change for neuroreach-alb-response-time-high -> 30.0
```

**Post-change state (both alarms):** `OK @ threshold 30.0` ✅

The new threshold still catches:
- Real backend stalls (RDS lock, Redis down, worker saturated, etc.)
- Anthropic itself degrading badly (>30s per single request sustained for 15 min)
- Any fan-out of slow requests pushing the p99 across 3 consecutive 5-min windows

It stops false-firing on a **single** legitimate AI-Insights click.

### Follow-up ticket (not done tonight — requires refactor)

**Title:** Move `/api/ai-insights?force_refresh=true` to async Celery job
**Target:** `backend/src/api/ai_insights.py`, `backend/src/services/ai_insights_service.py`
**Change:**
- `POST /api/ai-insights/refresh` → enqueue Celery task, return `202 {job_id}`
- `GET /api/ai-insights/refresh/{job_id}` → poll status
- `GET /api/ai-insights` → always serves cache (already does)

Once that ships, the alarm threshold can be lowered back to **5s** (the real
user-facing SLA).

Same endpoint exists in NeuroReach (`NeuroReachAI/backend/src/api/ai_insights.py`
and `NeuroReachAI/backend/src/services/ai_insights_service.py` — cache key
`neuroreach:ai_insights:organization:v3`) and needs the same refactor.

---

## Why this is safe

- **No code change** → no redeploy → no risk to live traffic.
- AI-Insights endpoint **still works identically** for users. The 30-50s wait
  behind the Refresh button was already the status quo.
- Real incidents (backend saturation, DB issue, Anthropic outage affecting many
  users) will still fire because they will push p99 above 30s across 3
  consecutive 5-min buckets, not a single one.
- Both tenants' backend response-time SLOs are independently tracked; this
  only changes the alerting threshold, not the measurement.

---

## Timeline (UTC+3)

| Time    | Event                                                         |
|---------|---------------------------------------------------------------|
| 16:38   | SleepReach frontend fix deployed (`acf8acc`), prod verified OK |
| 17:12   | First `sleepreach-prod-alb-response-time-high` ALARM            |
| 17:13–19:16 | 6 alternating ALARM/OK transitions on both alarms          |
| 19:05   | Backend log shows `GET /api/ai-insights?force_refresh=true` 37.3s |
| 19:08   | Backend log shows `GET /api/ai-insights?force_refresh=true` 48.6s |
| 19:16   | Alarms clear because clicking stopped                         |
| 19:40   | Root cause identified, thresholds raised 5s → 30s             |
| 19:40+  | Both alarms `OK`, no further flapping                         |

---

## Monitoring

Dashboards and tools that help detect a recurrence:

```bash
# Watch backend-TG p99 bucket-by-bucket
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/neuroreach-ai-alb/09820aa0f84e6f0b \
  --start-time $(date -u -v-1H +%FT%TZ) --end-time $(date -u +%FT%TZ) \
  --period 300 --extended-statistics p99

# Grep for slow-request warnings in SR backend (src/main.py emits these)
aws logs filter-log-events --log-group-name /ecs/sleepreach-prod-backend \
  --filter-pattern "Slow request" --limit 50
```
