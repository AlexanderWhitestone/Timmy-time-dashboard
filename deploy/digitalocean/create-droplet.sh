#!/usr/bin/env bash
set -euo pipefail

# ── Timmy Time — DigitalOcean Droplet Creator ────────────────────────────────
#
# Creates a DigitalOcean Droplet with Timmy pre-installed via cloud-init.
#
# Prerequisites:
#   - doctl CLI installed (https://docs.digitalocean.com/reference/doctl/)
#   - doctl auth init (authenticated)
#
# Usage:
#   bash deploy/digitalocean/create-droplet.sh
#   bash deploy/digitalocean/create-droplet.sh --domain timmy.example.com
#   bash deploy/digitalocean/create-droplet.sh --size s-2vcpu-4gb --region nyc1

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

# Defaults
DROPLET_NAME="timmy-mission-control"
REGION="nyc1"
SIZE="s-2vcpu-4gb"    # 2 vCPU, 4GB RAM — good for llama3.2
IMAGE="ubuntu-24-04-x64"
DOMAIN=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)     DROPLET_NAME="$2"; shift 2 ;;
        --region)   REGION="$2"; shift 2 ;;
        --size)     SIZE="$2"; shift 2 ;;
        --domain)   DOMAIN="$2"; shift 2 ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check doctl
if ! command -v doctl &> /dev/null; then
    echo "Error: doctl is not installed."
    echo "Install it: https://docs.digitalocean.com/reference/doctl/how-to/install/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_INIT="$SCRIPT_DIR/../cloud-init.yaml"

if [ ! -f "$CLOUD_INIT" ]; then
    echo "Error: cloud-init.yaml not found at $CLOUD_INIT"
    exit 1
fi

echo -e "${CYAN}${BOLD}"
echo "  Creating DigitalOcean Droplet"
echo "  ─────────────────────────────"
echo -e "${NC}"
echo "  Name:   $DROPLET_NAME"
echo "  Region: $REGION"
echo "  Size:   $SIZE"
echo "  Image:  $IMAGE"
echo ""

# Create the droplet
DROPLET_ID=$(doctl compute droplet create "$DROPLET_NAME" \
    --region "$REGION" \
    --size "$SIZE" \
    --image "$IMAGE" \
    --user-data-file "$CLOUD_INIT" \
    --enable-monitoring \
    --format ID \
    --no-header \
    --wait)

echo -e "${GREEN}[+]${NC} Droplet created: ID $DROPLET_ID"

# Get the IP
sleep 5
IP=$(doctl compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)
echo -e "${GREEN}[+]${NC} Public IP: $IP"

# Set up DNS if domain provided
if [ -n "$DOMAIN" ]; then
    # Extract the base domain (last two parts)
    BASE_DOMAIN=$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')
    SUBDOMAIN=$(echo "$DOMAIN" | sed "s/\.$BASE_DOMAIN$//")

    if [ "$SUBDOMAIN" = "$DOMAIN" ]; then
        SUBDOMAIN="@"
    fi

    echo -e "${GREEN}[+]${NC} Creating DNS record: $DOMAIN -> $IP"
    doctl compute domain records create "$BASE_DOMAIN" \
        --record-type A \
        --record-name "$SUBDOMAIN" \
        --record-data "$IP" \
        --record-ttl 300 || echo "  (DNS record creation failed — set it manually)"
fi

echo ""
echo -e "${GREEN}${BOLD}  Droplet is provisioning!${NC}"
echo ""
echo "  The server will be ready in ~3-5 minutes."
echo ""
echo "  SSH in:          ssh root@$IP"
echo "  Check progress:  ssh root@$IP tail -f /var/log/cloud-init-output.log"
if [ -n "$DOMAIN" ]; then
    echo "  Dashboard:       https://$DOMAIN  (after DNS propagation)"
fi
echo "  Dashboard:       http://$IP"
echo ""
echo "  After boot, edit /opt/timmy/.env to set your domain and secrets."
echo ""
