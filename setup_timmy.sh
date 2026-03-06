#!/usr/bin/env bash

# =============================================================================
# Sovereign Agent Stack — VPS Deployment Script (Remote-Ready Version v5)
#
# A single file to bootstrap Paperclip + OpenFang + Obsidian on a VPS.
#
# Usage:
#   1. curl -O https://raw.githubusercontent.com/AlexanderWhitestone/Timmy-time-dashboard/main/setup_timmy.sh
#   2. chmod +x setup_timmy.sh
#   3. ./setup_timmy.sh install
#   4. ./setup_timmy.sh start
#
# Dashboard: http://YOUR_VPS_IP:3100
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="${PROJECT_DIR:-$HOME/sovereign-stack}"
VAULT_DIR="${VAULT_DIR:-$PROJECT_DIR/TimmyVault}"
PAPERCLIP_DIR="$PROJECT_DIR/paperclip"
AGENTS_DIR="$PROJECT_DIR/agents"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

# Database Configuration (System Postgres)
DB_USER="paperclip"
DB_PASS="paperclip"
DB_NAME="paperclip"
DATABASE_URL="postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"

# --- Colors ---
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# --- Helper Functions ---
banner() { echo -e "\n${CYAN}═══════════════════════════════════════════════${NC}\n${BOLD}$1${NC}\n${CYAN}═══════════════════════════════════════════════${NC}\n"; }
step()   { echo -e "${GREEN}▸${NC} $1"; }
warn()   { echo -e "${YELLOW}⚠${NC} $1"; }
error()  { echo -e "${RED}✘${NC} $1"; exit 1; }
info()   { echo -e "${BOLD}$1${NC}"; }

# --- Core Logic ---

check_preflight() {
    banner "Preflight Checks"
    
    # Check OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        step "OS: Linux detected ✓"
    else
        warn "OS: $OSTYPE detected. This script is optimized for Ubuntu/Debian."
    fi

    # Install basic dependencies if missing (Ubuntu/Debian only)
    if command -v apt-get >/dev/null 2>&1; then
        step "Updating system and installing base dependencies..."
        sudo apt-get update -y > /dev/null
        sudo apt-get install -y curl git postgresql postgresql-contrib build-essential > /dev/null
    fi

    # Check for Node.js
    if ! command -v node >/dev/null 2>&1; then
        step "Installing Node.js 20..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
    step "Node $(node -v) ✓"

    # Check for pnpm
    if ! command -v pnpm >/dev/null 2>&1; then
        step "Installing pnpm..."
        sudo npm install -g pnpm
    fi
    step "pnpm $(pnpm -v) ✓"
}

setup_database() {
    banner "Database Setup"
    step "Ensuring PostgreSQL service is running..."
    sudo service postgresql start || true
    
    step "Configuring Paperclip database and user..."
    # Create user and database if they don't exist
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' SUPERUSER;"
    
    sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
        
    step "Database ready ✓"
}

install_stack() {
    banner "Installing Sovereign Stack"
    mkdir -p "$PROJECT_DIR" "$AGENTS_DIR" "$LOG_DIR" "$PID_DIR"

    # 1. OpenFang
    if ! command -v openfang >/dev/null 2>&1; then
        step "Installing OpenFang..."
        curl -fsSL https://openfang.sh/install | sh
    fi
    step "OpenFang ready ✓"

    # 2. Paperclip
    if [ ! -d "$PAPERCLIP_DIR" ]; then
        step "Cloning Paperclip..."
        git clone --depth 1 https://github.com/paperclipai/paperclip.git "$PAPERCLIP_DIR"
    fi
    cd "$PAPERCLIP_DIR"
    step "Installing Paperclip dependencies (this may take a few minutes)..."
    pnpm install --frozen-lockfile 2>/dev/null || pnpm install
    cd - > /dev/null
    step "Paperclip ready ✓"

    # 3. Obsidian Vault
    mkdir -p "$VAULT_DIR"
    if [ ! -f "$VAULT_DIR/Genesis.md" ]; then
        echo "# Genesis Note" > "$VAULT_DIR/Genesis.md"
        echo "Created on $(date)" >> "$VAULT_DIR/Genesis.md"
    fi
    step "Obsidian Vault ready: $VAULT_DIR ✓"
}

start_services() {
    banner "Starting Services"
    
    # Start Paperclip
    if [ -f "$PID_DIR/paperclip.pid" ] && ps -p $(cat "$PID_DIR/paperclip.pid") > /dev/null; then
        warn "Paperclip is already running."
    else
        step "Starting Paperclip (binding to 0.0.0.0)..."
        cd "$PAPERCLIP_DIR"
        
        # --- Remote Access Configuration ---
        PUBLIC_IP=$(curl -s ifconfig.me)
        export DATABASE_URL="$DATABASE_URL"
        export BETTER_AUTH_SECRET="sovereign-$(openssl rand -hex 16)"
        export PAPERCLIP_AGENT_JWT_SECRET="agent-$(openssl rand -hex 16)"
        export BETTER_AUTH_URL="http://$PUBLIC_IP:3100"
        
        # Security: Allow the public IP hostname
        export PAPERCLIP_ALLOWED_HOSTNAMES="$PUBLIC_IP,localhost,127.0.0.1"
        
        nohup pnpm dev --authenticated-private > "$LOG_DIR/paperclip.log" 2>&1 &
        echo $! > "$PID_DIR/paperclip.pid"
        cd - > /dev/null
    fi

    # Start OpenFang
    if [ -f "$PID_DIR/openfang.pid" ] && ps -p $(cat "$PID_DIR/openfang.pid") > /dev/null; then
        warn "OpenFang is already running."
    else
        step "Starting OpenFang..."
        nohup openfang start > "$LOG_DIR/openfang.log" 2>&1 &
        echo $! > "$PID_DIR/openfang.pid"
    fi

    step "Waiting for Paperclip to initialize..."
    for i in {1..30}; do
        if grep -q "Server listening on" "$LOG_DIR/paperclip.log" 2>/dev/null; then
            info "SUCCESS: Paperclip is live!"
            info "Dashboard: http://$(curl -s ifconfig.me):3100"
            return
        fi
        sleep 2
    done
    warn "Startup taking longer than expected. Check logs: $LOG_DIR/paperclip.log"
}

stop_services() {
    banner "Stopping Services"
    for service in paperclip openfang; do
        pid_file="$PID_DIR/$service.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            step "Stopping $service (PID: $pid)..."
            pkill -P "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
            rm "$pid_file"
        fi
    done
    step "Services stopped ✓"
}

# --- Main CLI ---

case "${1:-}" in
    install)
        check_preflight
        setup_database
        install_stack
        banner "Installation Complete"
        info "Run: ./setup_timmy.sh start"
        ;;
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    status)
        banner "Stack Status"
        for s in paperclip openfang; do
            if [ -f "$PID_DIR/$s.pid" ] && ps -p $(cat "$PID_DIR/$s.pid") > /dev/null; then
                echo -e "${GREEN}●${NC} $s is running"
            else
                echo -e "${RED}○${NC} $s is stopped"
            fi
        done
        ;;
    logs)
        tail -f "$LOG_DIR"/*.log
        ;;
    *)
        echo "Usage: $0 {install|start|stop|status|logs}"
        exit 1
        ;;
esac
