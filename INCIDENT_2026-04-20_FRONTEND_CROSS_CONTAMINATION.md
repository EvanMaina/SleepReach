# Incident: SleepReach Frontend Served NeuroReach UI (Prod)

**Date:** 2026-04-20
**Severity:** P1 — Wrong tenant UI served in production
**Environment:** `app.sleeplessinarizona.com` (SleepReach prod)
**Duration of wrong UI:** ~14:45 → ~16:25 UTC+3 (~1h40m)
**Backend / Database / API impact:** NONE (unchanged throughout)

---

## Summary

`app.sleeplessinarizona.com` was serving the **NeuroReach AI** frontend
(NeuroReach sidebar, NR analytics, `<title>NeuroReach AI - Patient Intake</title>`)
instead of the SleepReach UI. Staging (`stg.sleeplessinarizona.com`) was
unaffected and continued to correctly serve SleepReach.

Backend (`api.sleeplessinarizona.com`) was healthy and unaffected. No
SleepReach lead / patient / database records were touched.

---

## Root Cause

The ECS service `sleepreach-prod-frontend` (task def rev 20) was pointed at
ECR image:

```
131880217305.dkr.ecr.us-east-2.amazonaws.com/sleepreach/frontend:prod-506e6aa
```

`506e6aa` is a **NeuroReach main-branch SHA**, NOT a SleepReach SHA
(SleepReach's main tip is `372c2dd`). A NeuroReach image was built and
pushed to the SleepReach ECR repository, then promoted to the SleepReach
production ECS service.

### How the cross-contamination happened

During a prior QA session the local SleepReach working copy's
`.git/config` `origin` URL got flipped to
`https://github.com/EvanMaina/NeuroReachAI.git` (both repos live under
OneDrive, so OneDrive occasionally resurrects an older `.git/config`).
During a manual deploy kickoff against what was believed to be the
SleepReach checkout, the build was in fact running from NeuroReach
source, tagged `prod-<sha>` using SleepReach's ECR env vars, and pushed
to the `sleepreach/frontend` repository.

Evidence:
- SleepReach `sleepreach/frontend` ECR contains both correct
  `prod-372c2dd` (14:27) and contaminant `prod-506e6aa` (14:45).
- `506e6aa` does NOT exist in SleepReach git history; it is NeuroReach's
  main tip.
- Live HTML served by `app.` matched NeuroReach's bundle exactly
  (`<title>NeuroReach AI - Patient Intake</title>`).

---

## Remediation (applied)

1. Verified correct SleepReach image `prod-372c2dd` was already present in
   `sleepreach/frontend` ECR (digest
   `sha256:e8ebc89972a9e4022d2cd4ce054bf6ad83e6556bf3e101c8078ba7ec74f27ca2`).
2. Registered new task def revision
   `arn:aws:ecs:us-east-2:131880217305:task-definition/sleepreach-prod-frontend:21`
   pointing at `prod-372c2dd`.
3. `aws ecs update-service --force-new-deployment` on `sleepreach-prod-frontend`.
4. Deployment reached `rolloutState: COMPLETED`, desired=running=1.
5. Re-curled `https://app.sleeplessinarizona.com/` →
   `<title>SleepReach</title>` ✅
6. Re-curled `https://stg.sleeplessinarizona.com/` → SleepReach ✅
   (was already correct).
7. Re-curled `https://api.sleeplessinarizona.com/health` →
   `{"status":"healthy","database":"connected","environment":"production"}` ✅
8. Repointed local `.git/config` origin back to
   `https://github.com/EvanMaina/SleepReach.git`.

---

## Preventive measures (follow-up)

- [ ] Build step in `deploy-production.yml` / `deploy-staging.yml` should
  hard-assert the remote URL matches `EvanMaina/SleepReach` before any
  `docker push` to `sleepreach/*` ECR repos. Example:

  ```yaml
  - name: Assert repo identity
    run: |
      REMOTE=$(git remote get-url origin)
      case "$REMOTE" in
        *EvanMaina/SleepReach*) echo "✅ SleepReach repo confirmed";;
        *) echo "❌ Wrong origin: $REMOTE"; exit 1;;
      esac
  ```

  (Same guard in NeuroReach deploy workflows, pinned to NeuroReachAI.)

- [ ] Bake the tool name into the built bundle via `VITE_APP_NAME` env in
  the deploy workflow and surface it on `/version` or in the nginx
  response header so a wrong-bundle deploy is visible from HTTP alone.

- [ ] Move both repos out of OneDrive-synced folders onto
  `C:\src\SleepReach` and `C:\src\NeuroReachAI` to eliminate OneDrive
  `.git/config` rewrites.

- [ ] Separate ECR push IAM: SleepReach CI role may only push to
  `sleepreach/*`; NeuroReach CI role only to `neuroreach-ai/*`.
