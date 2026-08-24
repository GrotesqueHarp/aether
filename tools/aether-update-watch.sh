#!/usr/bin/env bash
#
# aether-update-watch.sh — the host half of the in-game update button.
#
# AETHER runs in a container with no git, no docker CLI and no docker socket,
# which is deliberate: docker-compose.yml uses host networking and the API has
# no authentication, so anything on your LAN can reach it. A container that
# could run `docker compose` would be a container that could hand out root on
# this machine to anyone who found port 8787.
#
# So the game never applies its own update. It writes a request file onto the
# shared /data volume; this script runs on the HOST, notices the file, and runs
# update.sh itself. The only thing crossing the boundary is an empty file.
#
#   ./aether-update-watch.sh --once     check once and exit (what the timer runs)
#   ./aether-update-watch.sh --watch    poll forever (handy for testing)
#   ./aether-update-watch.sh --status   print what it can see, change nothing
#
# Env:
#   AETHER_REPO   path to the aether checkout   (default: this script's parent)
#   AETHER_DATA   path to the data volume       (default: auto-detected)
#   POLL_SECONDS  --watch poll interval         (default: 20)

set -uo pipefail

REPO="${AETHER_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
POLL_SECONDS="${POLL_SECONDS:-20}"

detect_data() {
    if [[ -n "${AETHER_DATA:-}" ]]; then echo "$AETHER_DATA"; return; fi
    # named volume from docker-compose.yml, however the project prefixed it
    local v
    v="$(docker volume ls --format '{{.Name}}' 2>/dev/null \
         | grep -E '(^|_)aether_data$' | head -1 || true)"
    if [[ -n "$v" ]]; then
        docker volume inspect "$v" --format '{{.Mountpoint}}' 2>/dev/null && return
    fi
    echo "/var/lib/docker/volumes/aether_data/_data"
}

DATA="$(detect_data)"
REQUEST="$DATA/update-request"
STATUS="$DATA/update-status.json"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

# The game reads this to know whether anyone is listening. No heartbeat, and
# the UI says "helper not installed" instead of offering a button that would
# silently do nothing.
write_status() {   # state ok message [from] [to]
    local state="$1" ok="$2" msg="$3" from="${4:-}" to="${5:-}" now
    now="$(date +%s)"
    # Valid JSON without needing jq or python on the host — every message here
    # is ours, but strip the two characters that could break quoting anyway.
    msg="${msg//\\/}";   msg="${msg//\"/}"
    from="${from//\"/}"; to="${to//\"/}"
    mkdir -p "$DATA" 2>/dev/null || true
    cat > "$STATUS.tmp" <<EOF
{"state":"$state","ok":$ok,"message":"$msg","heartbeat":$now,"finished":$now,"from":"$from","to":"$to"}
EOF
    # Atomic: the game may read this at any moment, and half a JSON file
    # would read as "no helper installed".
    mv -f "$STATUS.tmp" "$STATUS"
}

if [[ ! -d "$DATA" ]]; then
    log "ERROR: data volume not found at $DATA"
    log "       set AETHER_DATA=/path/to/volume (see: docker volume inspect aether_data)"
    exit 1
fi

case "${1:---once}" in
  --status)
    log "repo:   $REPO"
    log "data:   $DATA"
    log "request pending: $([[ -f $REQUEST ]] && echo yes || echo no)"
    [[ -f "$STATUS" ]] && { log "last status:"; cat "$STATUS"; }
    exit 0
    ;;
esac

run_update() {
    local from to
    from="$(cat "$REPO/VERSION" 2>/dev/null || echo '?')"
    log "update requested (from v$from) — running update.sh"
    write_status working true "applying update" "$from"

    local out rc
    # `bash update.sh`, not `./update.sh`: update.sh is stored 100644 in the
    # repo, so a fresh clone has no executable bit and ./ would die with
    # "permission denied" — with the request file already consumed.
    out="$(cd "$REPO" && bash ./update.sh 2>&1)"; rc=$?
    to="$(cat "$REPO/VERSION" 2>/dev/null || echo '?')"

    # Clear the request FIRST: update.sh restarts the container, and a request
    # left behind would be picked up again on the next tick — an update loop.
    rm -f "$REQUEST"

    if [[ $rc -eq 0 ]]; then
        log "update ok (v$from -> v$to)"
        write_status idle true "updated to v$to" "$from" "$to"
    else
        log "update FAILED (exit $rc)"
        printf '%s\n' "$out" | tail -20
        write_status idle false "update.sh failed (exit $rc) — check the host log" "$from" "$to"
    fi
}

once() {
    if [[ -f "$REQUEST" ]]; then
        run_update
    else
        # Heartbeat only. This is what tells the game a helper is alive.
        write_status idle true "waiting"
    fi
}

case "${1:---once}" in
  --once)  once ;;
  --watch) log "watching $REQUEST every ${POLL_SECONDS}s"
           while true; do once; sleep "$POLL_SECONDS"; done ;;
  *)       log "usage: $0 [--once|--watch|--status]"; exit 2 ;;
esac
