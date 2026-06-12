#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Zero-downtime deploy (called after a code push or update)
#
# Usage:
#   bash infra/deploy/deploy.sh
#
# Steps:
#   1. Build fresh images (--pull to update base layers)
#   2. Run Alembic database migrations
#   3. Rolling restart of api + worker (leaves other services untouched)
#   4. Verify health
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENTIS_HOME="${AGENTIS_HOME:-/opt/agentis}"
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
COMPOSE_FILES="--compatibility -f docker-compose.yml -f docker-compose.prod.yml"
SERVICES_TO_RESTART="api worker"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $*" >&2; }

# ---------------------------------------------------------------------------
# Change to repo root
# ---------------------------------------------------------------------------
cd "${APP_DIR}"

if [[ ! -f "docker-compose.yml" ]]; then
    log_error "docker-compose.yml not found in ${APP_DIR}. Are you in the right directory?"
    exit 1
fi

DEPLOY_START=$(date +%s)
log_info "=== Agentis deploy started at $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# ===========================================================================
# 1. Pull & build images
# ===========================================================================
log_info "Building images (pulling latest base layers)..."
docker compose ${COMPOSE_FILES} build --pull --parallel api worker ui
log_success "Images built."

# ===========================================================================
# 2. Run Alembic database migrations (one-off container, auto-removed)
# ===========================================================================
log_info "Running database migrations..."
docker compose ${COMPOSE_FILES} run --rm \
    --no-deps \
    api \
    alembic upgrade head
log_success "Migrations applied."

# ===========================================================================
# 3. Rolling restart of stateless services (api + worker)
#    --no-deps: don't restart dependencies (postgres, redis, qdrant)
#    --build:   use the freshly built image
# ===========================================================================
log_info "Rolling restart of: ${SERVICES_TO_RESTART}..."
# shellcheck disable=SC2086
docker compose ${COMPOSE_FILES} up -d --no-deps --build ${SERVICES_TO_RESTART}
log_success "Services restarted."

# ===========================================================================
# 4. Health check — wait up to 60 s for the API to become healthy
# ===========================================================================
log_info "Waiting for API health check..."
ATTEMPTS=0
MAX_ATTEMPTS=20
SLEEP_S=3

until docker compose ${COMPOSE_FILES} exec -T api \
        curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [[ ${ATTEMPTS} -ge ${MAX_ATTEMPTS} ]]; then
        log_error "API did not become healthy within $((MAX_ATTEMPTS * SLEEP_S)) seconds."
        log_error "Check logs: docker compose logs --tail=50 api"
        exit 1
    fi
    log_info "  Not ready yet, retrying in ${SLEEP_S}s (attempt ${ATTEMPTS}/${MAX_ATTEMPTS})..."
    sleep "${SLEEP_S}"
done

log_success "API is healthy."

# ===========================================================================
# 5. Summary
# ===========================================================================
DEPLOY_END=$(date +%s)
ELAPSED=$((DEPLOY_END - DEPLOY_START))

log_success ""
log_success "============================================================"
log_success "  Deploy complete in ${ELAPSED}s"
log_success "  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
log_success ""
log_success "  Running containers:"
docker compose ${COMPOSE_FILES} ps --format "table {{.Name}}\t{{.Status}}"
log_success "============================================================"
