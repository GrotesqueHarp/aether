#!/usr/bin/env bash
#
# install.sh — AETHER setup for Debian / Debian-derived systems
#
#   ./install.sh              check + install system dependencies
#   ./install.sh --service    …and also install a systemd service (needs root)
#   ./install.sh --check      dry run: report what's missing, change nothing
#
# AETHER ships its Python dependencies in ./vendor (pure Python, works on x86
# and ARM), so there is NO pip and NO virtualenv involved. This script only
# ensures the system tools exist:
#
#   python3 (>= 3.9)   runs the game
#   iputils-ping       warms the ARP cache during network scans
#   iproute2 (ip)      reads the ARP/neighbour table
#
# Idempotent: safe to re-run any time.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${AETHER_PORT:-8787}"
SERVICE_NAME="aether"

MODE="install"
[[ "${1:-}" == "--check" ]] && MODE="check"
[[ "${1:-}" == "--service" ]] && MODE="service"

# ---------------------------------------------------------------- helpers ---
c_ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
c_miss() { printf '  \033[33m✗\033[0m %s\n' "$1"; }
c_err()  { printf '\033[31mERROR:\033[0m %s\n' "$1" >&2; }
c_head() { printf '\n\033[1m%s\033[0m\n' "$1"; }

have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
need_root_for_apt() {
    if [[ $EUID -ne 0 ]]; then
        if have sudo; then SUDO="sudo"
        else
            c_err "Installing packages requires root. Re-run as root or install sudo."
            exit 1
        fi
    fi
}

# ------------------------------------------------------------ environment ---
c_head "AETHER installer — Debian environment check"

if ! have apt-get; then
    c_err "apt-get not found. This script targets Debian/Ubuntu-family systems."
    c_err "Manual deps: python3 (>=3.9), iputils-ping, iproute2. Then: python3 app.py"
    exit 1
fi

if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    c_ok "Detected: ${PRETTY_NAME:-unknown Debian-like system}"
fi

# -------------------------------------------------------- dependency scan ---
c_head "Checking dependencies"

APT_PKGS=()

if have python3; then
    PYVER="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then
        c_ok "python3 $PYVER"
    else
        c_miss "python3 $PYVER is too old (need >= 3.9)"; APT_PKGS+=(python3)
    fi
else
    c_miss "python3"; APT_PKGS+=(python3)
fi

if have ping; then
    c_ok "ping (iputils-ping)"
else
    c_miss "ping — needed to warm the ARP cache when scanning"; APT_PKGS+=(iputils-ping)
fi

if have ip; then
    c_ok "ip (iproute2)"
else
    c_miss "ip — needed to read the ARP/neighbour table"; APT_PKGS+=(iproute2)
fi

# bundled Python deps
if [[ -d "$APP_DIR/vendor/flask" ]]; then
    c_ok "bundled Python packages present (./vendor)"
    VENDOR_OK=1
else
    VENDOR_OK=0
    if python3 -c 'import flask' 2>/dev/null; then
        c_ok "flask available system-wide (./vendor missing but not needed)"
    else
        c_miss "./vendor directory missing AND flask not installed — re-download the full package"
    fi
fi

have arp  && c_ok "arp (net-tools) — optional fallback present"
have curl && c_ok "curl (optional) present"

# ----------------------------------------------------------------- report ---
if [[ "$MODE" == "check" ]]; then
    c_head "Dry run complete"
    if [[ ${#APT_PKGS[@]} -gt 0 ]]; then
        echo "  Would install via apt: ${APT_PKGS[*]}"
    else
        echo "  All system dependencies satisfied. Nothing to do."
    fi
    exit 0
fi

# ------------------------------------------------------------ apt install ---
if [[ ${#APT_PKGS[@]} -gt 0 ]]; then
    c_head "Installing missing packages: ${APT_PKGS[*]}"
    need_root_for_apt
    export DEBIAN_FRONTEND=noninteractive
    # A single broken third-party repo shouldn't block us — update best-effort,
    # then let the install itself be the real test.
    $SUDO apt-get update -qq 2>/dev/null || \
        echo "  (apt-get update reported errors — likely an unrelated repo; continuing)"
    if ! $SUDO apt-get install -y -qq "${APT_PKGS[@]}"; then
        c_err "apt-get install failed for: ${APT_PKGS[*]}"
        c_err "Fix your apt sources (or install these packages manually) and re-run."
        exit 1
    fi
    c_ok "System packages installed"
else
    c_head "All system dependencies already satisfied"
fi

# ---------------------------------------------------------- runnability -----
c_head "Verifying AETHER can run"
if (cd "$APP_DIR" && python3 - <<'PYEOF'
import os, sys
sys.path.insert(0, os.getcwd())
vendor = os.path.join(os.getcwd(), "vendor")
try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    if os.path.isdir(vendor):
        sys.path.insert(0, vendor)
        import flask  # noqa: F401
    else:
        raise
from core import seed, world, battle, ticker, scan, db  # noqa: F401
PYEOF
); then
    c_ok "Flask resolves (system or bundled) and the game core imports cleanly"
else
    c_err "AETHER failed its import check — the package may be incomplete."
    exit 1
fi

# -------------------------------------------------------- systemd service ---
if [[ "$MODE" == "service" ]]; then
    c_head "Installing systemd service"
    if [[ $EUID -ne 0 ]] && ! have sudo; then
        c_err "--service needs root (or sudo)."; exit 1
    fi
    need_root_for_apt
    if ! have systemctl; then
        c_err "systemd not found (common in some LXC containers)."
        c_err "Run AETHER directly instead: python3 $APP_DIR/app.py"
        exit 1
    fi
    RUN_USER="${SUDO_USER:-$(id -un)}"
    PY_BIN="$(command -v python3)"
    UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
    $SUDO tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=AETHER — LAN daemon-raising game
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
Environment=AETHER_PORT=$PORT
ExecStart=$PY_BIN $APP_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now "$SERVICE_NAME"
    c_ok "Service '$SERVICE_NAME' installed and started"
    echo "     status:  systemctl status $SERVICE_NAME"
    echo "     logs:    journalctl -u $SERVICE_NAME -f"
fi

# ------------------------------------------------------------------ done ----
LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -n1 || true)"
c_head "Done"
if [[ "$MODE" != "service" ]]; then
    echo "  Start AETHER:   python3 $APP_DIR/app.py"
fi
echo "  Then open:      http://${LAN_IP:-<your-lan-ip>}:$PORT  (from any device on your network)"
echo
echo "  Tips:"
echo "    • firewall (ufw):  sudo ufw allow ${PORT}/tcp"
echo "    • re-run this script any time; it only fixes what's missing"
echo "    • ./install.sh --service to run AETHER on boot via systemd"
