#!/usr/bin/env bash
# =============================================================================
# update.sh — Pull latest code and re-deploy Agentis
#
# Usage:
#   bash infra/deploy/update.sh
#   bash infra/deploy/update.sh main        # explicit branch
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BRANCH="${1:-main}"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $*"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $*" >&2; }

# ---------------------------------------------------------------------------
# Change to repo root
# ---------------------------------------------------------------------------
cd "${APP_DIR}"

if [[ ! -d ".git" ]]; then
    log_error "Not a git repository: ${APP_DIR}"
    log_error "If you deployed via rsync, run deploy.sh directly."
    exit 1
fi

log_info "=== Agentis update started at $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# ===========================================================================
# 1. Stash any local changes to avoid merge conflicts on .env / generated files
# ===========================================================================
log_info "Checking for local modifications..."
if ! git diff --quiet HEAD 2>/dev/null; then
    log_info "Stashing local modifications..."
    git stash push -m "auto-stash before update $(date +%s)"
fi

# ===========================================================================
# 2. Pull latest code
# ===========================================================================
log_info "Pulling origin/${BRANCH}..."
git fetch --tags origin "${BRANCH}"
git checkout "${BRANCH}"
git merge --ff-only "origin/${BRANCH}"
log_success "Code updated to: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"

# ===========================================================================
# 3. Re-deploy
# ===========================================================================
log_info "Calling deploy.sh..."
bash "$(dirname "${BASH_SOURCE[0]}")/deploy.sh"
