#!/usr/bin/env bash
# =============================================================================
# install.sh — Initial Agentis server setup for a fresh Debian VPS
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/your-org/agentis/main/infra/deploy/install.sh | sudo bash
#   # OR clone the repo first, then:
#   sudo bash infra/deploy/install.sh
#
# Idempotent: safe to re-run; already-installed components are skipped.
# Tested on: Debian 12 (Bookworm), Debian 11 (Bullseye)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable variables
# ---------------------------------------------------------------------------
AGENTIS_USER="agentis"
AGENTIS_GROUP="agentis"
AGENTIS_HOME="/opt/agentis"
REPO_URL="${REPO_URL:-https://github.com/your-org/agentis.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

# Script directory (if running from a cloned repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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
# Must run as root
# ---------------------------------------------------------------------------
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log_error "This script must be run as root (or with sudo)."
    exit 1
fi

log_info "Starting Agentis installation on $(lsb_release -ds 2>/dev/null || uname -sr)"

# ===========================================================================
# 1. System dependencies
# ===========================================================================
log_info "Updating package lists..."
apt-get update -qq

log_info "Installing prerequisite packages..."
apt-get install -y -qq \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    openssl \
    python3 \
    python3-pip \
    rsync \
    jq \
    netcat-openbsd \
    2>/dev/null

# ===========================================================================
# 2. Install Docker (official apt repo)
# ===========================================================================
if command -v docker &>/dev/null; then
    log_success "Docker already installed: $(docker --version)"
else
    log_info "Installing Docker from official apt repository..."

    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the stable channel apt repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian \
        $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable --now docker
    log_success "Docker installed: $(docker --version)"
fi

# Verify Docker Compose v2 plugin is available
if ! docker compose version &>/dev/null; then
    log_error "Docker Compose plugin not found. Install docker-compose-plugin manually."
    exit 1
fi
log_success "Docker Compose: $(docker compose version --short)"

# ===========================================================================
# 3. Create agentis system user and group
# ===========================================================================
if ! getent group "${AGENTIS_GROUP}" &>/dev/null; then
    log_info "Creating group: ${AGENTIS_GROUP}"
    groupadd --system "${AGENTIS_GROUP}"
fi

if ! id "${AGENTIS_USER}" &>/dev/null; then
    log_info "Creating user: ${AGENTIS_USER}"
    useradd --system --gid "${AGENTIS_GROUP}" \
            --home-dir "${AGENTIS_HOME}" \
            --no-create-home \
            --shell /usr/sbin/nologin \
            "${AGENTIS_USER}"
fi

# Add agentis user to the docker group so compose runs without sudo
usermod -aG docker "${AGENTIS_USER}"
log_success "User ${AGENTIS_USER} ready."

# ===========================================================================
# 4. Create directory structure
# ===========================================================================
log_info "Creating directory structure at ${AGENTIS_HOME}..."

dirs=(
    "${AGENTIS_HOME}"
    "${AGENTIS_HOME}/app"
    "${AGENTIS_HOME}/secrets/jwt"
    "${AGENTIS_HOME}/secrets/fernet"
    "${AGENTIS_HOME}/logs"
    "${AGENTIS_HOME}/data/postgres"
    "${AGENTIS_HOME}/data/qdrant"
    "${AGENTIS_HOME}/data/minio"
    "${AGENTIS_HOME}/data/caddy"
)

for dir in "${dirs[@]}"; do
    mkdir -p "${dir}"
done

chown -R "${AGENTIS_USER}:${AGENTIS_GROUP}" "${AGENTIS_HOME}"
chmod 750 "${AGENTIS_HOME}/secrets"
chmod 700 "${AGENTIS_HOME}/secrets/jwt"
chmod 700 "${AGENTIS_HOME}/secrets/fernet"

log_success "Directories created."

# ===========================================================================
# 5. Clone or rsync the repository into /opt/agentis/app
# ===========================================================================
APP_DIR="${AGENTIS_HOME}/app"

if [[ -d "${REPO_ROOT}/.git" && "${REPO_ROOT}" != "${APP_DIR}" ]]; then
    # Running from a cloned repo — rsync it
    log_info "Syncing repository from ${REPO_ROOT} to ${APP_DIR}..."
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='node_modules' \
        --exclude='.next' \
        "${REPO_ROOT}/" "${APP_DIR}/"
else
    # Clone fresh
    if [[ -d "${APP_DIR}/.git" ]]; then
        log_info "Repository already cloned — pulling latest..."
        git -C "${APP_DIR}" pull origin "${REPO_BRANCH}"
    else
        log_info "Cloning ${REPO_URL} (branch: ${REPO_BRANCH})..."
        git clone --branch "${REPO_BRANCH}" --depth 1 "${REPO_URL}" "${APP_DIR}"
    fi
fi

chown -R "${AGENTIS_USER}:${AGENTIS_GROUP}" "${APP_DIR}"
log_success "Repository ready at ${APP_DIR}."

# ===========================================================================
# 6. Configure .env
# ===========================================================================
ENV_FILE="${APP_DIR}/.env"
ENV_EXAMPLE="${APP_DIR}/.env.example"

if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f "${ENV_EXAMPLE}" ]]; then
        log_info "Copying .env.example to .env..."
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        chown "${AGENTIS_USER}:${AGENTIS_GROUP}" "${ENV_FILE}"
        chmod 640 "${ENV_FILE}"
        log_warn "IMPORTANT: Edit ${ENV_FILE} and fill in all CHANGE_ME placeholders before starting."
        log_warn "Press ENTER to open the file in your default editor (or Ctrl-C to skip)."
        read -r _ || true
        "${EDITOR:-nano}" "${ENV_FILE}" || true
    else
        log_warn ".env.example not found — you must create ${ENV_FILE} manually."
    fi
else
    log_success ".env already exists, skipping copy."
fi

# ===========================================================================
# 7. Generate RSA 4096 JWT key pair
# ===========================================================================
JWT_DIR="${AGENTIS_HOME}/secrets/jwt"
PRIVATE_KEY="${JWT_DIR}/private.pem"
PUBLIC_KEY="${JWT_DIR}/public.pem"

if [[ -f "${PRIVATE_KEY}" && -f "${PUBLIC_KEY}" ]]; then
    log_success "JWT key pair already exists — skipping generation."
else
    log_info "Generating RSA 4096 JWT key pair..."
    openssl genrsa -out "${PRIVATE_KEY}" 4096 2>/dev/null
    openssl rsa -in "${PRIVATE_KEY}" -pubout -out "${PUBLIC_KEY}" 2>/dev/null
    chmod 600 "${PRIVATE_KEY}"
    chmod 644 "${PUBLIC_KEY}"
    chown "${AGENTIS_USER}:${AGENTIS_GROUP}" "${PRIVATE_KEY}" "${PUBLIC_KEY}"
    log_success "JWT keys generated:"
    log_success "  Private: ${PRIVATE_KEY}"
    log_success "  Public:  ${PUBLIC_KEY}"
fi

# Symlink keys into the app directory so Docker bind-mount paths work
APP_SECRETS="${APP_DIR}/secrets/jwt"
mkdir -p "${APP_SECRETS}"
if [[ ! -L "${APP_SECRETS}/private.pem" ]]; then
    ln -sf "${PRIVATE_KEY}" "${APP_SECRETS}/private.pem"
fi
if [[ ! -L "${APP_SECRETS}/public.pem" ]]; then
    ln -sf "${PUBLIC_KEY}" "${APP_SECRETS}/public.pem"
fi
chown -h "${AGENTIS_USER}:${AGENTIS_GROUP}" "${APP_SECRETS}/private.pem" "${APP_SECRETS}/public.pem"

# ===========================================================================
# 8. Generate Fernet key
# ===========================================================================
log_info "Generating Fernet key for webhook secret encryption..."
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)

if [[ -n "${FERNET_KEY}" ]]; then
    echo ""
    echo "============================================================"
    echo "  FERNET KEY (set AGENTIS_FERNET_KEY in .env):"
    echo ""
    echo "  ${FERNET_KEY}"
    echo ""
    echo "  Store this key securely — losing it means webhook secrets"
    echo "  stored in the DB cannot be decrypted."
    echo "============================================================"
    echo ""

    # Auto-update .env if the placeholder is still present
    if [[ -f "${ENV_FILE}" ]] && grep -q "CHANGE_ME_base64_fernet_key_here" "${ENV_FILE}"; then
        sed -i "s|AGENTIS_FERNET_KEY=CHANGE_ME_base64_fernet_key_here|AGENTIS_FERNET_KEY=${FERNET_KEY}|" "${ENV_FILE}"
        log_success "AGENTIS_FERNET_KEY automatically set in ${ENV_FILE}"
    fi
else
    log_warn "Could not generate Fernet key — cryptography package not installed."
    log_warn "Install it and run:"
    log_warn "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    log_warn "Then set AGENTIS_FERNET_KEY in ${ENV_FILE}"
fi

# ===========================================================================
# 9. Create Caddyfile template if not present
# ===========================================================================
CADDYFILE="${APP_DIR}/infra/Caddyfile"
if [[ ! -f "${CADDYFILE}" ]]; then
    log_info "Creating Caddyfile template at ${CADDYFILE}..."
    mkdir -p "$(dirname "${CADDYFILE}")"
    cat > "${CADDYFILE}" <<'CADDYEOF'
# Replace agentis.example.com with your actual domain.
# Caddy will automatically obtain a Let's Encrypt TLS certificate.

agentis.example.com {
    # API backend
    handle /api/* {
        reverse_proxy api:8000
    }
    handle /health {
        reverse_proxy api:8000
    }
    handle /docs {
        reverse_proxy api:8000
    }
    handle /openapi.json {
        reverse_proxy api:8000
    }
    # WebSocket (HITL)
    handle /ws/* {
        reverse_proxy api:8000
    }
    # Frontend (Next.js)
    handle {
        reverse_proxy ui:3000
    }
    encode gzip
    log {
        output file /data/caddy-access.log {
            roll_size 50mb
            roll_keep 5
        }
    }
}
CADDYEOF
    chown "${AGENTIS_USER}:${AGENTIS_GROUP}" "${CADDYFILE}"
    log_warn "Edit ${CADDYFILE} to set your domain before starting."
fi

# ===========================================================================
# 10. Start Agentis
# ===========================================================================
log_info "Starting Agentis stack..."
cd "${APP_DIR}"

# Ensure .env exists before bringing up containers
if [[ ! -f "${ENV_FILE}" ]]; then
    log_error ".env file not found at ${ENV_FILE}. Cannot start. Please create it first."
    exit 1
fi

if grep -qE "CHANGE_ME|REDIS_PASS_HERE" "${ENV_FILE}"; then
    log_warn "WARNING: .env still contains placeholder values."
    log_warn "Press ENTER to start anyway (NOT RECOMMENDED for production), or Ctrl-C to abort."
    read -r _ || true
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

log_success ""
log_success "============================================================"
log_success "  Agentis is starting!"
log_success ""
log_success "  Check status:  docker compose ps"
log_success "  View logs:     docker compose logs -f api"
log_success "  Deploy update: bash ${APP_DIR}/infra/deploy/deploy.sh"
log_success "============================================================"
