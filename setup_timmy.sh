#!/usr/bin/env bash

# =============================================================================
# Sovereign Agent Stack — VPS Deployment Script v8
#
# Hermes Agent + Paperclip, Tailscale-only.
#   - Hermes Agent (Nous Research) — persistent AI agent
#   - Paperclip in local_trusted mode (127.0.0.1:3100)
#   - Nginx reverse proxy on Tailscale IP (port 80)
#   - Cookie-based auth gate for Paperclip
#   - PostgreSQL backend
#   - UFW locked to Tailscale + SSH only
#   - systemd services for auto-restart
#   - Daily backups with 30-day retention
#
# Usage:
#   ./setup_timmy.sh install    # Full install (run once on fresh VPS)
#   ./setup_timmy.sh start      # Start all services
#   ./setup_timmy.sh stop       # Stop all services
#   ./setup_timmy.sh restart    # Stop + start
#   ./setup_timmy.sh status     # Health check
#   ./setup_timmy.sh logs       # Tail all logs
#
# Prerequisites:
#   - Ubuntu 22.04+ VPS with root access
#   - Tailscale installed and joined to tailnet
#   - SSH key added
#
# Access (Tailscale only):
#   Paperclip: http://<TAILSCALE_IP>
#   Hermes:    ssh to VPS, then `hermes`
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="${PROJECT_DIR:-$HOME/sovereign-stack}"
PAPERCLIP_DIR="$PROJECT_DIR/paperclip"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"
BACKUP_DIR="$HOME/backups/hermes"

# Tailscale IP (auto-detected)
TSIP="${TSIP:-$(tailscale ip -4 2>/dev/null || echo '127.0.0.1')}"

DB_USER="paperclip"
DB_PASS="paperclip"
DB_NAME="paperclip"
DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"

AUTH_USER="${AUTH_USER:-Rockachopa}"
AUTH_PASS="${AUTH_PASS:-Iamrockachopathegend}"

SECRETS_FILE="$PROJECT_DIR/.secrets"

# --- Colors ---
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

banner() { echo -e "\n${CYAN}═══════════════════════════════════════════════${NC}\n${BOLD}$1${NC}\n${CYAN}═══════════════════════════════════════════════${NC}\n"; }
step()   { echo -e "${GREEN}▸${NC} $1"; }
warn()   { echo -e "${YELLOW}⚠${NC} $1"; }
fail()   { echo -e "${RED}✘${NC} $1"; exit 1; }
info()   { echo -e "${BOLD}$1${NC}"; }

# =============================================================================
# INSTALL
# =============================================================================

check_preflight() {
    banner "Preflight"

    # Tailscale must be connected
    if [ "$TSIP" = "127.0.0.1" ]; then
        fail "Tailscale not connected. Run: tailscale up --authkey=YOUR_KEY"
    fi
    step "Tailscale IP: $TSIP"

    if command -v apt-get >/dev/null 2>&1; then
        step "Installing system packages..."
        apt-get update -y > /dev/null 2>&1
        apt-get install -y curl git postgresql postgresql-contrib build-essential nginx lsof > /dev/null 2>&1
    fi

    # Node.js 20
    if ! command -v node >/dev/null 2>&1; then
        step "Installing Node.js 20..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
        apt-get install -y nodejs > /dev/null 2>&1
    fi
    step "Node $(node -v)"

    # pnpm
    if ! command -v pnpm >/dev/null 2>&1; then
        step "Installing pnpm..."
        npm install -g pnpm > /dev/null 2>&1
    fi
    step "pnpm $(pnpm -v)"

    # uv (for Hermes)
    if ! command -v uv >/dev/null 2>&1 && [ ! -f "$HOME/.local/bin/uv" ]; then
        step "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null 2>&1
    fi
    export PATH="$HOME/.local/bin:$PATH"
    step "uv ready"
}

# --- Database ---
setup_database() {
    banner "Database"
    systemctl start postgresql || service postgresql start || true

    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' SUPERUSER;"

    sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

    step "Database ready"
}

# --- Hermes Agent ---
install_hermes() {
    banner "Hermes Agent"

    if [ -d "$HOME/.hermes/hermes-agent" ]; then
        step "Hermes already cloned, updating..."
        cd "$HOME/.hermes/hermes-agent" && git pull origin main 2>/dev/null || true
        cd - > /dev/null
    else
        step "Installing Hermes (one-liner)..."
        curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup
    fi

    # Ensure venv exists
    export PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$PATH"
    if [ ! -d "$HOME/.hermes/hermes-agent/.venv" ]; then
        step "Creating Hermes venv..."
        cd "$HOME/.hermes/hermes-agent"
        uv venv .venv --python 3.12 2>/dev/null || uv venv .venv
        source .venv/bin/activate
        uv pip install -e ".[all]" 2>&1 | tail -3
        cd - > /dev/null
    fi

    # Add hermes to PATH in bashrc if not already there
    if ! grep -q 'hermes-agent/.venv/bin' "$HOME/.bashrc" 2>/dev/null; then
        cat >> "$HOME/.bashrc" <<'BASHRC'

# Sovereign Stack — Hermes Agent
export PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$HOME/.hermes/hermes-agent/.venv/bin:$PATH"
alias hermes='cd ~/.hermes/hermes-agent && source .venv/bin/activate && python hermes'
BASHRC
    fi

    step "Hermes installed"
}

# --- Auth Gate ---
install_auth_gate() {
    step "Installing auth gate..."

    cat > "$PROJECT_DIR/auth-gate.py" <<'AUTHGATE'
#!/usr/bin/env python3
"""Cookie-based auth gate. Login once, 7-day session."""
import hashlib, hmac, http.server, time, base64, os

SECRET = os.environ.get("AUTH_GATE_SECRET", "sovereign-timmy-gate-2026")
USER = os.environ.get("AUTH_USER", "admin")
PASS = os.environ.get("AUTH_PASS", "changeme")
COOKIE_NAME = "sovereign_gate"
COOKIE_MAX_AGE = 86400 * 7

def make_token(ts):
    return hmac.new(SECRET.encode(), f"{USER}:{ts}".encode(), hashlib.sha256).hexdigest()[:32]

def verify_token(token):
    try:
        parts = token.split(".")
        if len(parts) != 2: return False
        ts, sig = int(parts[0]), parts[1]
        if time.time() - ts > COOKIE_MAX_AGE: return False
        return sig == make_token(ts)
    except: return False

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        for c in self.headers.get("Cookie", "").split(";"):
            c = c.strip()
            if c.startswith(f"{COOKIE_NAME}=") and verify_token(c[len(COOKIE_NAME)+1:]):
                self.send_response(200); self.end_headers(); return
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                u, p = base64.b64decode(auth[6:]).decode().split(":", 1)
                if u == USER and p == PASS:
                    ts = int(time.time())
                    self.send_response(200)
                    self.send_header("Set-Cookie",
                        f"{COOKIE_NAME}={ts}.{make_token(ts)}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; SameSite=Lax")
                    self.end_headers(); return
            except: pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Sovereign Stack"')
        self.end_headers()

if __name__ == "__main__":
    s = http.server.HTTPServer(("127.0.0.1", 9876), Handler)
    print("Auth gate on 127.0.0.1:9876"); s.serve_forever()
AUTHGATE
    chmod +x "$PROJECT_DIR/auth-gate.py"
}

# --- Nginx (Tailscale-only) ---
install_nginx() {
    step "Configuring nginx (Tailscale-only: $TSIP)..."

    cat > /etc/nginx/sites-available/paperclip <<NGINX
server {
    listen ${TSIP}:80;

    location = /_auth {
        internal;
        proxy_pass http://127.0.0.1:9876;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI \$request_uri;
        proxy_set_header Cookie \$http_cookie;
        proxy_set_header Authorization \$http_authorization;
    }

    location / {
        auth_request /_auth;
        auth_request_set \$auth_cookie \$upstream_http_set_cookie;
        add_header Set-Cookie \$auth_cookie;

        proxy_pass http://127.0.0.1:3100;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host localhost;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }

    error_page 401 = @login;
    location @login {
        proxy_pass http://127.0.0.1:9876;
        proxy_set_header Authorization \$http_authorization;
        proxy_set_header Cookie \$http_cookie;
    }
}
NGINX

    ln -sf /etc/nginx/sites-available/paperclip /etc/nginx/sites-enabled/paperclip
    rm -f /etc/nginx/sites-enabled/default
    nginx -t || fail "Nginx config failed"
}

# --- UFW (SSH first, then lockdown) ---
setup_firewall() {
    banner "Firewall"
    step "Allowing SSH before lockdown..."
    ufw allow 22/tcp
    ufw allow in on tailscale0
    ufw allow in on lo
    ufw default deny incoming
    ufw default allow outgoing
    ufw --force enable
    step "Firewall locked: SSH + Tailscale only"
}

# --- Secrets ---
load_or_create_secrets() {
    if [ -f "$SECRETS_FILE" ]; then
        source "$SECRETS_FILE"
        step "Loaded secrets"
    else
        BETTER_AUTH_SECRET="sovereign-$(openssl rand -hex 16)"
        PAPERCLIP_AGENT_JWT_SECRET="agent-$(openssl rand -hex 16)"
        cat > "$SECRETS_FILE" <<SECRETS
BETTER_AUTH_SECRET="$BETTER_AUTH_SECRET"
PAPERCLIP_AGENT_JWT_SECRET="$PAPERCLIP_AGENT_JWT_SECRET"
SECRETS
        chmod 600 "$SECRETS_FILE"
        step "Generated secrets"
    fi
}

# --- Paperclip ---
install_paperclip() {
    banner "Paperclip"
    mkdir -p "$PROJECT_DIR" "$LOG_DIR" "$PID_DIR"

    if [ ! -d "$PAPERCLIP_DIR" ]; then
        step "Cloning Paperclip..."
        git clone --depth 1 https://github.com/paperclipai/paperclip.git "$PAPERCLIP_DIR"
    fi
    cd "$PAPERCLIP_DIR"
    step "Installing dependencies..."
    pnpm install --frozen-lockfile 2>/dev/null || pnpm install
    cd - > /dev/null

    install_auth_gate
    install_nginx
    step "Paperclip installed"
}

# --- systemd services ---
install_systemd() {
    banner "systemd Services"

    # Auth gate
    cat > /etc/systemd/system/sovereign-auth-gate.service <<UNIT
[Unit]
Description=Sovereign Auth Gate
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PROJECT_DIR/auth-gate.py
Environment=AUTH_USER=$AUTH_USER
Environment=AUTH_PASS=$AUTH_PASS
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

    # Paperclip
    cat > /etc/systemd/system/sovereign-paperclip.service <<UNIT
[Unit]
Description=Paperclip Dashboard
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=$PAPERCLIP_DIR
ExecStart=$(which pnpm) dev
Environment=HOST=127.0.0.1
Environment=DATABASE_URL=$DATABASE_URL
Environment=PAPERCLIP_DEPLOYMENT_MODE=local_trusted
Environment=BETTER_AUTH_URL=http://$TSIP
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

    # Hermes gateway
    cat > /etc/systemd/system/hermes-gateway.service <<UNIT
[Unit]
Description=Hermes Agent Gateway
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$HOME/.hermes/hermes-agent
ExecStart=$HOME/.hermes/hermes-agent/.venv/bin/python hermes gateway
Environment=HERMES_BIND_HOST=$TSIP
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

    # Load secrets into paperclip service
    if [ -f "$SECRETS_FILE" ]; then
        source "$SECRETS_FILE"
        mkdir -p /etc/systemd/system/sovereign-paperclip.service.d
        cat > /etc/systemd/system/sovereign-paperclip.service.d/secrets.conf <<OVERRIDE
[Service]
Environment=BETTER_AUTH_SECRET=$BETTER_AUTH_SECRET
Environment=PAPERCLIP_AGENT_JWT_SECRET=$PAPERCLIP_AGENT_JWT_SECRET
OVERRIDE
    fi

    systemctl daemon-reload
    systemctl enable sovereign-auth-gate sovereign-paperclip hermes-gateway
    step "systemd services installed and enabled"
}

# --- Backups ---
install_backups() {
    banner "Backups"
    mkdir -p "$BACKUP_DIR"

    cat > "$HOME/scripts/hermes-backup.sh" <<'BACKUP'
#!/bin/bash
BACKUP_DIR=$HOME/backups/hermes
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HERMES_HOME=$HOME/.hermes

mkdir -p $BACKUP_DIR

tar czf $BACKUP_DIR/hermes_$TIMESTAMP.tar.gz \
    $HERMES_HOME/config.yaml \
    $HERMES_HOME/.env \
    $HERMES_HOME/hermes-agent/skills/ \
    $HERMES_HOME/hermes-agent/sessions/ \
    $HERMES_HOME/cron/ \
    2>/dev/null || true

# Prune backups older than 30 days
find $BACKUP_DIR -name 'hermes_*.tar.gz' -mtime +30 -delete

echo "$(date): Backup complete: hermes_$TIMESTAMP.tar.gz"
BACKUP
    mkdir -p "$HOME/scripts"
    chmod +x "$HOME/scripts/hermes-backup.sh"

    # Cron: daily at 3 AM
    (crontab -l 2>/dev/null | grep -v hermes-backup; echo "0 3 * * * $HOME/scripts/hermes-backup.sh >> /var/log/hermes-backup.log 2>&1") | crontab -

    step "Daily backup at 3 AM, 30-day retention"
}

# =============================================================================
# RUNTIME
# =============================================================================

kill_zombies() {
    step "Cleaning stale processes..."
    for port in 3100 3101 3102 3103 3104 3105 9876; do
        pid=$(lsof -ti :$port 2>/dev/null || true)
        [ -n "$pid" ] && kill -9 $pid 2>/dev/null && step "Killed port $port" || true
    done
    sleep 1
}

start_services() {
    banner "Starting"
    load_or_create_secrets
    kill_zombies

    systemctl restart sovereign-auth-gate
    systemctl restart nginx
    systemctl restart sovereign-paperclip

    step "Waiting for Paperclip..."
    for i in $(seq 1 30); do
        if systemctl is-active --quiet sovereign-paperclip && curl -s -o /dev/null http://127.0.0.1:3100 2>/dev/null; then
            break
        fi
        printf "."; sleep 2
    done
    echo ""

    info "══════════════════════════════════════"
    info "  Paperclip: http://$TSIP"
    info "  Hermes:    ssh root@$TSIP → hermes"
    info "  Auth:      $AUTH_USER / ********"
    info "══════════════════════════════════════"
}

stop_services() {
    banner "Stopping"
    systemctl stop sovereign-paperclip 2>/dev/null || true
    systemctl stop sovereign-auth-gate 2>/dev/null || true
    systemctl stop hermes-gateway 2>/dev/null || true
    step "All services stopped"
}

show_status() {
    banner "Status"
    for svc in sovereign-auth-gate sovereign-paperclip hermes-gateway nginx postgresql; do
        if systemctl is-active --quiet $svc 2>/dev/null; then
            echo -e "  ${GREEN}●${NC} $svc"
        else
            echo -e "  ${RED}○${NC} $svc"
        fi
    done
    echo ""
    echo -e "  Tailscale: $TSIP"
    echo -e "  Paperclip: http://$TSIP"
    echo ""
    for port in 80 3100 9876; do
        if lsof -ti :$port > /dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} :$port"
        else
            echo -e "  ${RED}○${NC} :$port"
        fi
    done
}

# =============================================================================
# FULL INSTALL (run once)
# =============================================================================
full_install() {
    check_preflight
    setup_database
    install_hermes
    install_paperclip
    load_or_create_secrets
    install_systemd
    install_backups
    setup_firewall

    banner "Install Complete"
    info "Run: ./setup_timmy.sh start"
}

# --- CLI ---
case "${1:-}" in
    install)  full_install ;;
    start)    start_services ;;
    stop)     stop_services ;;
    restart)  stop_services; sleep 2; start_services ;;
    status)   show_status ;;
    logs)     journalctl -u sovereign-paperclip -u sovereign-auth-gate -u hermes-gateway -f ;;
    *)        echo "Usage: $0 {install|start|stop|restart|status|logs}"; exit 1 ;;
esac
