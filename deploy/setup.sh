#!/usr/bin/env bash
set -euo pipefail

# ── Timmy Time — One-Click Deploy Script ─────────────────────────────────────
#
# Run this on any fresh Ubuntu/Debian server:
#
#   curl -fsSL https://raw.githubusercontent.com/AlexanderWhitestone/Timmy-time-dashboard/master/deploy/setup.sh | bash
#
# Or clone first and run locally:
#
#   git clone https://github.com/AlexanderWhitestone/Timmy-time-dashboard.git
#   cd Timmy-time-dashboard
#   bash deploy/setup.sh
#
# What it does:
#   1. Installs Docker (if not present)
#   2. Configures firewall
#   3. Generates secrets
#   4. Builds and starts the full stack
#   5. Pulls the LLM model
#   6. Sets up auto-start on boot

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="/opt/timmy"

banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║     Timmy Time — Mission Control         ║"
    echo "  ║     One-Click Cloud Deploy               ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()    { echo -e "${GREEN}[+]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[x]${NC} $1"; }
step()    { echo -e "\n${BOLD}── $1 ──${NC}"; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "This script must be run as root (or with sudo)"
        exit 1
    fi
}

generate_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
    openssl rand -hex 32 2>/dev/null || \
    head -c 32 /dev/urandom | xxd -p -c 64
}

install_docker() {
    step "Installing Docker"
    if command -v docker &> /dev/null; then
        info "Docker already installed: $(docker --version)"
    else
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker
        systemctl start docker
        info "Docker installed: $(docker --version)"
    fi

    # Ensure docker compose plugin is available
    if ! docker compose version &> /dev/null; then
        error "Docker Compose plugin not found. Please install it manually."
        exit 1
    fi
    info "Docker Compose: $(docker compose version --short)"
}

setup_firewall() {
    step "Configuring Firewall"
    if command -v ufw &> /dev/null; then
        ufw default deny incoming
        ufw default allow outgoing
        ufw allow 22/tcp    # SSH
        ufw allow 80/tcp    # HTTP
        ufw allow 443/tcp   # HTTPS
        ufw allow 443/udp   # HTTP/3
        ufw --force enable
        info "Firewall configured (SSH, HTTP, HTTPS)"
    else
        warn "ufw not found — install it or configure your firewall manually"
    fi
}

setup_fail2ban() {
    step "Setting up Fail2ban"
    if command -v fail2ban-server &> /dev/null; then
        systemctl enable fail2ban
        systemctl start fail2ban
        info "Fail2ban active"
    else
        apt-get install -y fail2ban 2>/dev/null && systemctl enable fail2ban && systemctl start fail2ban && info "Fail2ban installed and active" || \
        warn "Could not install fail2ban — install manually for SSH protection"
    fi
}

clone_or_update() {
    step "Setting up Timmy"
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Existing installation found at $INSTALL_DIR — updating..."
        cd "$INSTALL_DIR"
        git pull origin master || git pull origin main || warn "Could not pull updates"
    elif [ -f "./docker-compose.prod.yml" ]; then
        info "Running from repo directory — copying to $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        cp -r . "$INSTALL_DIR/"
        cd "$INSTALL_DIR"
    else
        info "Cloning Timmy Time Dashboard..."
        git clone https://github.com/AlexanderWhitestone/Timmy-time-dashboard.git "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
    mkdir -p data
}

configure_env() {
    step "Configuring Environment"
    local ENV_FILE="$INSTALL_DIR/.env"

    if [ -f "$ENV_FILE" ]; then
        warn ".env already exists — skipping (edit manually if needed)"
        return
    fi

    # Interactive domain setup
    local DOMAIN="localhost"
    echo ""
    read -rp "  Enter your domain (or press Enter for IP-only access): " USER_DOMAIN
    if [ -n "$USER_DOMAIN" ]; then
        DOMAIN="$USER_DOMAIN"
    fi

    # Interactive model selection
    local MODEL="llama3.2"
    echo ""
    echo "  Available LLM models:"
    echo "    1) llama3.2      (~2GB, fast, good for most tasks)"
    echo "    2) llama3.1:8b   (~4.7GB, better reasoning)"
    echo "    3) mistral       (~4.1GB, good all-rounder)"
    echo "    4) phi3          (~2.2GB, compact and fast)"
    echo ""
    read -rp "  Select model [1-4, default=1]: " MODEL_CHOICE
    case "$MODEL_CHOICE" in
        2) MODEL="llama3.1:8b" ;;
        3) MODEL="mistral" ;;
        4) MODEL="phi3" ;;
        *) MODEL="llama3.2" ;;
    esac

    # Generate secrets
    local HMAC_SECRET
    HMAC_SECRET=$(generate_secret)
    local MACAROON_SECRET
    MACAROON_SECRET=$(generate_secret)

    cat > "$ENV_FILE" <<EOF
# ── Timmy Time — Production Environment ──────────────────────────────────────
# Generated by deploy/setup.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Domain for auto-HTTPS (set to your domain, or localhost for IP-only)
DOMAIN=$DOMAIN

# LLM model
OLLAMA_MODEL=$MODEL

# L402 Lightning secrets (auto-generated)
L402_HMAC_SECRET=$HMAC_SECRET
L402_MACAROON_SECRET=$MACAROON_SECRET

# Telegram bot token (optional — get from @BotFather)
TELEGRAM_TOKEN=

# Debug mode (set to true to enable /docs endpoint)
DEBUG=false
EOF

    chmod 600 "$ENV_FILE"
    info "Environment configured (secrets auto-generated)"
    info "Domain: $DOMAIN"
    info "Model: $MODEL"
}

build_and_start() {
    step "Building and Starting Timmy"
    cd "$INSTALL_DIR"
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d
    info "Stack is starting..."
}

pull_model() {
    step "Pulling LLM Model"
    local MODEL
    MODEL=$(grep -oP 'OLLAMA_MODEL=\K.*' "$INSTALL_DIR/.env" 2>/dev/null || echo "llama3.2")

    info "Waiting for Ollama to be ready..."
    local retries=0
    while [ $retries -lt 30 ]; do
        if docker exec timmy-ollama curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
            break
        fi
        sleep 5
        retries=$((retries + 1))
    done

    if [ $retries -ge 30 ]; then
        warn "Ollama not ready after 150s — pull model manually:"
        warn "  docker exec timmy-ollama ollama pull $MODEL"
        return
    fi

    info "Pulling $MODEL (this may take a few minutes)..."
    docker exec timmy-ollama ollama pull "$MODEL"
    info "Model $MODEL ready"
}

setup_systemd() {
    step "Enabling Auto-Start on Boot"
    cp "$INSTALL_DIR/deploy/timmy.service" /etc/systemd/system/timmy.service
    systemctl daemon-reload
    systemctl enable timmy
    info "Timmy will auto-start on reboot"
}

print_summary() {
    local DOMAIN
    DOMAIN=$(grep -oP 'DOMAIN=\K.*' "$INSTALL_DIR/.env" 2>/dev/null || echo "localhost")
    local IP
    IP=$(curl -4sf https://ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "your-server-ip")

    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║       Timmy is LIVE!                     ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    if [ "$DOMAIN" != "localhost" ]; then
        echo -e "  ${BOLD}Dashboard:${NC}  https://$DOMAIN"
    fi
    echo -e "  ${BOLD}Dashboard:${NC}  http://$IP"
    echo ""
    echo -e "  ${BOLD}Useful commands:${NC}"
    echo "    systemctl status timmy          # check status"
    echo "    systemctl restart timmy         # restart stack"
    echo "    docker compose -f /opt/timmy/docker-compose.prod.yml logs -f  # tail logs"
    echo "    nano /opt/timmy/.env            # edit config"
    echo ""
    echo -e "  ${BOLD}Scale agents:${NC}"
    echo "    cd /opt/timmy"
    echo "    docker compose -f docker-compose.prod.yml --profile agents up -d --scale agent=4"
    echo ""
    echo -e "  ${BOLD}Update Timmy:${NC}"
    echo "    cd /opt/timmy && git pull && docker compose -f docker-compose.prod.yml up -d --build"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────

banner
check_root
install_docker
setup_firewall
setup_fail2ban
clone_or_update
configure_env
build_and_start
pull_model
setup_systemd
print_summary
