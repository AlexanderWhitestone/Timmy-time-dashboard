#!/usr/bin/env bash

# =============================================================================
# Sovereign Agent Stack — VPS Deployment Script v6
#
# Bootstraps Paperclip + OpenFang + Obsidian Vault on a VPS with:
#   - Paperclip in local_trusted mode (127.0.0.1:3100)
#   - Nginx reverse proxy on port 80 with cookie-based auth gate
#   - One login prompt, 7-day session cookie — no repeated auth popups
#
# Usage:
#   1. curl -O https://raw.githubusercontent.com/AlexanderWhitestone/Timmy-time-dashboard/main/setup_timmy.sh
#   2. chmod +x setup_timmy.sh
#   3. ./setup_timmy.sh install
#   4. ./setup_timmy.sh start
#
# Dashboard: http://YOUR_DOMAIN (behind auth gate)
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="${PROJECT_DIR:-$HOME/sovereign-stack}"
VAULT_DIR="${VAULT_DIR:-$HOME/TimmyVault}"
PAPERCLIP_DIR="$PROJECT_DIR/paperclip"
AGENTS_DIR="$PROJECT_DIR/agents"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

# Domain / IP — set DOMAIN env var or edit here
DOMAIN="${DOMAIN:-$(curl -s ifconfig.me)}"

# Database
DB_USER="paperclip"
DB_PASS="paperclip"
DB_NAME="paperclip"
DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"

# Auth gate credentials — change these!
AUTH_USER="${AUTH_USER:-Rockachopa}"
AUTH_PASS="${AUTH_PASS:-Iamrockachopathegend}"

# Paperclip secrets (generated once, persisted in secrets file)
SECRETS_FILE="$PROJECT_DIR/.secrets"

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
fail()   { echo -e "${RED}✘${NC} $1"; exit 1; }
info()   { echo -e "${BOLD}$1${NC}"; }

# --- Secrets Management ---
load_or_create_secrets() {
    if [ -f "$SECRETS_FILE" ]; then
        source "$SECRETS_FILE"
        step "Loaded existing secrets"
    else
        BETTER_AUTH_SECRET="sovereign-$(openssl rand -hex 16)"
        PAPERCLIP_AGENT_JWT_SECRET="agent-$(openssl rand -hex 16)"
        cat > "$SECRETS_FILE" <<SECRETS
BETTER_AUTH_SECRET="$BETTER_AUTH_SECRET"
PAPERCLIP_AGENT_JWT_SECRET="$PAPERCLIP_AGENT_JWT_SECRET"
SECRETS
        chmod 600 "$SECRETS_FILE"
        step "Generated and saved new secrets"
    fi
}

# --- Preflight ---
check_preflight() {
    banner "Preflight Checks"

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        step "OS: Linux detected"
    else
        warn "OS: $OSTYPE — this script targets Ubuntu/Debian"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        step "Installing system dependencies..."
        sudo apt-get update -y > /dev/null 2>&1
        sudo apt-get install -y curl git postgresql postgresql-contrib build-essential nginx apache2-utils > /dev/null 2>&1
    fi

    if ! command -v node >/dev/null 2>&1; then
        step "Installing Node.js 20..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
        sudo apt-get install -y nodejs > /dev/null 2>&1
    fi
    step "Node $(node -v)"

    if ! command -v pnpm >/dev/null 2>&1; then
        step "Installing pnpm..."
        sudo npm install -g pnpm > /dev/null 2>&1
    fi
    step "pnpm $(pnpm -v)"
}

# --- Database ---
setup_database() {
    banner "Database Setup"
    step "Ensuring PostgreSQL is running..."
    sudo systemctl start postgresql || sudo service postgresql start || true

    step "Configuring database..."
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' SUPERUSER;"

    sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

    step "Database ready"
}

# --- Install Stack ---
install_stack() {
    banner "Installing Sovereign Stack"
    mkdir -p "$PROJECT_DIR" "$AGENTS_DIR" "$LOG_DIR" "$PID_DIR"

    # OpenFang
    if ! command -v openfang >/dev/null 2>&1; then
        step "Installing OpenFang..."
        curl -fsSL https://openfang.sh/install | sh
    fi
    step "OpenFang ready"

    # Paperclip
    if [ ! -d "$PAPERCLIP_DIR" ]; then
        step "Cloning Paperclip..."
        git clone --depth 1 https://github.com/paperclipai/paperclip.git "$PAPERCLIP_DIR"
    fi
    cd "$PAPERCLIP_DIR"
    step "Installing Paperclip dependencies..."
    pnpm install --frozen-lockfile 2>/dev/null || pnpm install
    cd - > /dev/null
    step "Paperclip ready"

    # Obsidian Vault
    mkdir -p "$VAULT_DIR"
    if [ ! -f "$VAULT_DIR/Genesis.md" ]; then
        cat > "$VAULT_DIR/Genesis.md" <<MD
# Genesis Note
Created on $(date)

Timmy's sovereign knowledge vault.
MD
    fi
    step "Obsidian Vault ready: $VAULT_DIR"

    # Install auth gate and nginx config
    install_auth_gate
    install_nginx

    banner "Installation Complete"
    info "Run: ./setup_timmy.sh start"
}

# --- Auth Gate (cookie-based, login once) ---
install_auth_gate() {
    step "Installing auth gate..."

    cat > "$PROJECT_DIR/auth-gate.py" <<'AUTHGATE'
#!/usr/bin/env python3
"""Cookie-based auth gate for nginx auth_request. Login once, session lasts 7 days."""
import hashlib, hmac, http.server, time, base64, os

SECRET = os.environ.get("AUTH_GATE_SECRET", "sovereign-timmy-gate-2026")
USER = os.environ.get("AUTH_USER", "admin")
PASS = os.environ.get("AUTH_PASS", "changeme")
COOKIE_NAME = "sovereign_gate"
COOKIE_MAX_AGE = 86400 * 7

def make_token(ts):
    msg = f"{USER}:{ts}".encode()
    return hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]

def verify_token(token):
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        ts, sig = int(parts[0]), parts[1]
        if time.time() - ts > COOKIE_MAX_AGE:
            return False
        return sig == make_token(ts)
    except:
        return False

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        cookies = self.headers.get("Cookie", "")
        for c in cookies.split(";"):
            c = c.strip()
            if c.startswith(f"{COOKIE_NAME}="):
                token = c[len(COOKIE_NAME)+1:]
                if verify_token(token):
                    self.send_response(200)
                    self.end_headers()
                    return

        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                u, p = decoded.split(":", 1)
                if u == USER and p == PASS:
                    ts = int(time.time())
                    token = f"{ts}.{make_token(ts)}"
                    self.send_response(200)
                    self.send_header("Set-Cookie",
                        f"{COOKIE_NAME}={token}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; SameSite=Lax")
                    self.end_headers()
                    return
            except:
                pass

        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Sovereign Stack"')
        self.end_headers()

if __name__ == "__main__":
    s = http.server.HTTPServer(("127.0.0.1", 9876), Handler)
    print("Auth gate listening on 127.0.0.1:9876")
    s.serve_forever()
AUTHGATE

    chmod +x "$PROJECT_DIR/auth-gate.py"
    step "Auth gate installed"
}

# --- Nginx Reverse Proxy ---
install_nginx() {
    step "Configuring nginx reverse proxy..."

    cat > /etc/nginx/sites-available/paperclip <<NGINX
server {
    listen 80;
    server_name $DOMAIN;

    # Cookie-based auth gate — login once, cookie lasts 7 days
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
        # Pass localhost as Host to bypass Vite's allowedHosts check
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
    nginx -t || fail "Nginx config test failed"
    step "Nginx configured"
}

# --- Process Cleanup ---
kill_zombies() {
    step "Cleaning up stale processes..."
    # Kill any existing Paperclip/node processes on ports 3100-3110
    for port in $(seq 3100 3110); do
        pid=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$pid" ]; then
            kill -9 $pid 2>/dev/null || true
            step "Killed process on port $port"
        fi
    done
    # Kill any stale auth gate
    pid=$(lsof -ti :9876 2>/dev/null || true)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
    fi
    sleep 1
}

# --- Start Services ---
start_services() {
    banner "Starting Services"

    load_or_create_secrets
    kill_zombies

    # Stop Docker Caddy if it's hogging port 80
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q timmy-caddy; then
        step "Stopping Docker Caddy (port 80 conflict)..."
        docker stop timmy-caddy > /dev/null 2>&1 || true
    fi

    # 1. Auth Gate
    step "Starting auth gate..."
    AUTH_USER="$AUTH_USER" AUTH_PASS="$AUTH_PASS" \
        nohup python3 "$PROJECT_DIR/auth-gate.py" > "$LOG_DIR/auth-gate.log" 2>&1 &
    echo $! > "$PID_DIR/auth-gate.pid"

    # 2. Nginx
    step "Starting nginx..."
    systemctl restart nginx

    # 3. Paperclip — local_trusted mode, bound to 127.0.0.1
    step "Starting Paperclip (local_trusted → 127.0.0.1:3100)..."
    cd "$PAPERCLIP_DIR"
    HOST=127.0.0.1 \
    DATABASE_URL="$DATABASE_URL" \
    PAPERCLIP_DEPLOYMENT_MODE=local_trusted \
    BETTER_AUTH_SECRET="$BETTER_AUTH_SECRET" \
    PAPERCLIP_AGENT_JWT_SECRET="$PAPERCLIP_AGENT_JWT_SECRET" \
    BETTER_AUTH_URL="http://$DOMAIN" \
        nohup pnpm dev > "$LOG_DIR/paperclip.log" 2>&1 &
    echo $! > "$PID_DIR/paperclip.pid"
    cd - > /dev/null

    # 4. OpenFang
    if command -v openfang >/dev/null 2>&1; then
        step "Starting OpenFang..."
        nohup openfang start > "$LOG_DIR/openfang.log" 2>&1 &
        echo $! > "$PID_DIR/openfang.pid"
    fi

    # Wait for Paperclip
    step "Waiting for Paperclip to initialize..."
    for i in $(seq 1 30); do
        if grep -q "Server listening on" "$LOG_DIR/paperclip.log" 2>/dev/null; then
            echo ""
            info "╔═══════════════════════════════════════════════╗"
            info "║  Sovereign Stack is LIVE                      ║"
            info "║                                               ║"
            info "║  Dashboard: http://$DOMAIN"
            info "║  Auth:      $AUTH_USER / ********              ║"
            info "║  Mode:      local_trusted + nginx proxy       ║"
            info "╚═══════════════════════════════════════════════╝"
            return
            fi
        printf "."
        sleep 2
    done
    echo ""
    warn "Startup taking longer than expected. Check: tail -f $LOG_DIR/paperclip.log"
}

# --- Stop Services ---
stop_services() {
    banner "Stopping Services"
    for service in paperclip openfang auth-gate; do
        pid_file="$PID_DIR/$service.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if ps -p "$pid" > /dev/null 2>&1; then
                step "Stopping $service (PID: $pid)..."
                kill "$pid" 2>/dev/null || true
                # Also kill child processes
                pkill -P "$pid" 2>/dev/null || true
            fi
            rm -f "$pid_file"
        fi
    done
    step "Services stopped"
}

# --- Status ---
show_status() {
    banner "Stack Status"
    for s in paperclip openfang auth-gate; do
        pid_file="$PID_DIR/$s.pid"
        if [ -f "$pid_file" ] && ps -p $(cat "$pid_file") > /dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} $s (PID $(cat "$pid_file"))"
        else
            echo -e "  ${RED}○${NC} $s"
        fi
    done

    echo ""
    # Port check
    for port in 80 3100 9876; do
        pid=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$pid" ]; then
            echo -e "  ${GREEN}●${NC} Port $port in use"
        else
            echo -e "  ${RED}○${NC} Port $port free"
        fi
    done

    echo ""
    if systemctl is-active --quiet nginx; then
        echo -e "  ${GREEN}●${NC} nginx active"
    else
        echo -e "  ${RED}○${NC} nginx inactive"
    fi
}

# --- Restart ---
restart_services() {
    stop_services
    sleep 2
    start_services
}

# --- Main CLI ---
case "${1:-}" in
    install)
        check_preflight
        setup_database
        install_stack
        ;;
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        tail -f "$LOG_DIR"/*.log
        ;;
    *)
        echo "Usage: $0 {install|start|stop|restart|status|logs}"
        exit 1
        ;;
esac
