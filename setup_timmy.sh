#!/usr/bin/env bash

# =============================================================================
# Sovereign Agent Stack — VPS Deployment Script v7
#
# Paperclip only. No fluff.
#   - Paperclip in local_trusted mode (127.0.0.1:3100)
#   - Nginx reverse proxy on port 80
#   - Cookie-based auth gate — login once, 7-day session
#   - PostgreSQL backend
#
# Usage:
#   curl -O https://raw.githubusercontent.com/AlexanderWhitestone/Timmy-time-dashboard/main/setup_timmy.sh
#   chmod +x setup_timmy.sh
#   ./setup_timmy.sh install
#   ./setup_timmy.sh start
#
# Dashboard: http://YOUR_DOMAIN (behind auth)
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="${PROJECT_DIR:-$HOME/sovereign-stack}"
PAPERCLIP_DIR="$PROJECT_DIR/paperclip"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

DOMAIN="${DOMAIN:-$(curl -s ifconfig.me)}"

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

# --- Preflight ---
check_preflight() {
    banner "Preflight"

    if command -v apt-get >/dev/null 2>&1; then
        step "Installing dependencies..."
        sudo apt-get update -y > /dev/null 2>&1
        sudo apt-get install -y curl git postgresql postgresql-contrib build-essential nginx > /dev/null 2>&1
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
    banner "Database"
    sudo systemctl start postgresql || sudo service postgresql start || true

    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' SUPERUSER;"

    sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

    step "Database ready"
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

# --- Nginx ---
install_nginx() {
    step "Configuring nginx..."

    cat > /etc/nginx/sites-available/paperclip <<NGINX
server {
    listen 80;
    server_name $DOMAIN;

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

# --- Install ---
install_stack() {
    banner "Installing Paperclip"
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

    banner "Installed"
    info "Run: ./setup_timmy.sh start"
}

# --- Cleanup ---
kill_zombies() {
    step "Cleaning stale processes..."
    for port in $(seq 3100 3110); do
        pid=$(lsof -ti :$port 2>/dev/null || true)
        [ -n "$pid" ] && kill -9 $pid 2>/dev/null && step "Killed port $port" || true
    done
    pid=$(lsof -ti :9876 2>/dev/null || true)
    [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
    sleep 1
}

# --- Start ---
start_services() {
    banner "Starting"
    load_or_create_secrets
    kill_zombies

    # Stop Docker Caddy if conflicting on port 80
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q timmy-caddy; then
        step "Stopping Docker Caddy (port 80)..."
        docker stop timmy-caddy > /dev/null 2>&1 || true
    fi

    step "Auth gate..."
    AUTH_USER="$AUTH_USER" AUTH_PASS="$AUTH_PASS" \
        nohup python3 "$PROJECT_DIR/auth-gate.py" > "$LOG_DIR/auth-gate.log" 2>&1 &
    echo $! > "$PID_DIR/auth-gate.pid"

    step "Nginx..."
    systemctl restart nginx

    step "Paperclip (local_trusted → 127.0.0.1:3100)..."
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

    step "Waiting for Paperclip..."
    for i in $(seq 1 30); do
        if grep -q "Server listening on" "$LOG_DIR/paperclip.log" 2>/dev/null; then
            echo ""
            info "══════════════════════════════════════"
            info "  Dashboard: http://$DOMAIN"
            info "  Auth:      $AUTH_USER / ********"
            info "══════════════════════════════════════"
            return
        fi
        printf "."; sleep 2
    done
    echo ""; warn "Slow start. Check: tail -f $LOG_DIR/paperclip.log"
}

# --- Stop ---
stop_services() {
    banner "Stopping"
    for service in paperclip auth-gate; do
        pid_file="$PID_DIR/$service.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            ps -p "$pid" > /dev/null 2>&1 && kill "$pid" 2>/dev/null && step "Stopped $service" || true
            rm -f "$pid_file"
        fi
    done
}

# --- Status ---
show_status() {
    banner "Status"
    for s in paperclip auth-gate; do
        pf="$PID_DIR/$s.pid"
        if [ -f "$pf" ] && ps -p $(cat "$pf") > /dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} $s"
        else
            echo -e "  ${RED}○${NC} $s"
        fi
    done
    echo ""
    for port in 80 3100 9876; do
        if lsof -ti :$port > /dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} :$port"
        else
            echo -e "  ${RED}○${NC} :$port"
        fi
    done
    echo ""
    systemctl is-active --quiet nginx && echo -e "  ${GREEN}●${NC} nginx" || echo -e "  ${RED}○${NC} nginx"
}

# --- CLI ---
case "${1:-}" in
    install)  check_preflight; setup_database; install_stack ;;
    start)    start_services ;;
    stop)     stop_services ;;
    restart)  stop_services; sleep 2; start_services ;;
    status)   show_status ;;
    logs)     tail -f "$LOG_DIR"/*.log ;;
    *)        echo "Usage: $0 {install|start|stop|restart|status|logs}"; exit 1 ;;
esac
