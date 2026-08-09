#!/usr/bin/env bash
#
# update.sh — apply an AETHER update when running under docker compose.
#
#   ./update.sh          pull latest code (if this is a git repo), rebuild, restart
#   ./update.sh --local  skip git pull; just rebuild from the files as they are
#                        (use after replacing files by hand / unzipping a new drop)
#
# Save data is untouched: it lives in the aether_data volume, and the app runs
# schema migrations automatically on startup, so old saves upgrade in place.

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

c_ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
c_err() { printf '\033[31mERROR:\033[0m %s\n' "$1" >&2; }

# docker compose v2 ("docker compose") vs v1 ("docker-compose")
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else c_err "docker compose not found"; exit 1; fi

OLD_VER="$(cat VERSION 2>/dev/null || echo '?')"

# 1. fetch new code
if [[ "${1:-}" != "--local" ]] && [[ -d .git ]]; then
    echo "Pulling latest…"
    git pull --ff-only
elif [[ "${1:-}" != "--local" ]]; then
    echo "(not a git repo — building from local files; tip: 'git init' this"
    echo " directory and push it somewhere so updates become 'git pull')"
fi

NEW_VER="$(cat VERSION 2>/dev/null || echo '?')"

# 2. rebuild + restart (compose only recreates if the image changed)
echo "Rebuilding image…"
$DC build --quiet
$DC up -d
c_ok "Container up (v$OLD_VER -> v$NEW_VER)"

# 3. verify it actually came back healthy
PORT="${AETHER_PORT:-8787}"
for i in $(seq 1 15); do
    if curl -sf -m 2 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
        LIVE_VER="$(curl -sf -m 2 "http://127.0.0.1:$PORT/api/state" \
                    | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || true)"
        c_ok "AETHER is serving (reports v${LIVE_VER:-?})"
        exit 0
    fi
    sleep 1
done
c_err "AETHER didn't respond on port $PORT after 15s — check: $DC logs aether"
exit 1
