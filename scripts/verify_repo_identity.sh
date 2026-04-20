#!/usr/bin/env bash
# =============================================================================
# verify_repo_identity.sh — SleepReach edition
#
# PURPOSE
# -------
# CI/CD guard that refuses to build if the working tree is NOT the SleepReach
# codebase. This prevents the cross-contamination incident (2026-04-20) where
# a NeuroReach build got pushed to sleepreach/frontend ECR and served on
# app.sleeplessinarizona.com (TD:25 + TD:27 served NR bundle). Root cause =
# workflows were copied between repos without updating identity markers and
# a NR prod deploy targeted SR infrastructure.
#
# HOW IT WORKS
# ------------
# Every SleepReach build MUST satisfy three independent markers:
#   1. git remote "origin" URL contains "SleepReach" (case-insensitive)
#   2. frontend/index.html <title> contains "SleepReach"
#   3. frontend/index.html does NOT contain "NeuroReach" or "tmsinstitute.co"
#
# If ANY check fails, the script exits 1 and the pipeline aborts BEFORE
# pushing anything to ECR or updating any ECS service. This means a NeuroReach
# tree can never be pushed to sleepreach/* repositories.
#
# Exit codes: 0 = SleepReach verified; 1 = contamination detected.
# =============================================================================
set -euo pipefail

EXPECTED_TOOL="SleepReach"
FORBIDDEN_TOKENS='NeuroReach\|tmsinstitute\.co'
FAIL=0

echo "=== Repo Identity Verification: ${EXPECTED_TOOL} ==="

# --- Check 1: git remote URL --------------------------------------------------
REMOTE_URL="$(git config --get remote.origin.url 2>/dev/null || echo 'NONE')"
echo "Check 1/3: git remote origin = ${REMOTE_URL}"
if echo "${REMOTE_URL}" | grep -iq "${EXPECTED_TOOL}"; then
  echo "  ✅ remote URL contains '${EXPECTED_TOOL}'"
else
  echo "  ❌ remote URL does NOT contain '${EXPECTED_TOOL}'"
  FAIL=1
fi

# --- Check 2: frontend/index.html <title> -------------------------------------
if [ -f frontend/index.html ]; then
  TITLE_LINE="$(grep -oiE '<title>[^<]*</title>' frontend/index.html | head -n1 || echo 'NO_TITLE')"
  echo "Check 2/3: frontend/index.html title = ${TITLE_LINE}"
  if echo "${TITLE_LINE}" | grep -iq "${EXPECTED_TOOL}"; then
    echo "  ✅ <title> contains '${EXPECTED_TOOL}'"
  else
    echo "  ❌ <title> does NOT contain '${EXPECTED_TOOL}' (contamination risk)"
    FAIL=1
  fi
else
  echo "Check 2/3: frontend/index.html MISSING"
  FAIL=1
fi

# --- Check 3: forbidden (other-tool) markers ----------------------------------
if [ -f frontend/index.html ]; then
  if grep -iq "${FORBIDDEN_TOKENS}" frontend/index.html; then
    echo "Check 3/3: ❌ frontend/index.html contains forbidden NeuroReach/tmsinstitute.co reference"
    grep -in "${FORBIDDEN_TOKENS}" frontend/index.html || true
    FAIL=1
  else
    echo "Check 3/3: ✅ no NeuroReach markers in frontend/index.html"
  fi
fi

echo "==================================================="
if [ "${FAIL}" -ne 0 ]; then
  echo "🚨 REPO IDENTITY CHECK FAILED — refusing to build."
  echo "   This working tree is NOT ${EXPECTED_TOOL}. Aborting before ECR push."
  exit 1
fi
echo "✅ Repo identity verified: ${EXPECTED_TOOL}"
exit 0
