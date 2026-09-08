#!/usr/bin/env bash
# ============================================================================
# LISTENER (run on the SECURE server only)
# Pulls new jobs from inbound and pushes back ONLY safe outbox results.
#
#   ./secure-bridge/receiver/listener.sh            # loop, default 20s
#   ./secure-bridge/receiver/listener.sh --once     # single pass
#   ./secure-bridge/receiver/listener.sh --push-outbox   # force a push of outbox
#   ./secure-bridge/receiver/listener.sh --daemon   # nohup loop in background
#
# Always runs git pull before processing, then processes fresh .py files in
# bridge-inbox/jobs/ and pushes output from bridge-outbox/ through the PHI
# gate. NEVER touches notebooks. NEVER stages raw data.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BRIDGE="$REPO_ROOT/secure-bridge"
INBOX="$BRIDGE/bridge-inbox/jobs"
OUTBOX="$BRIDGE/bridge-outbox"
STATE="$BRIDGE/bridge-state"
LOG="$STATE/bridge.log"
POLL=20
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
MODE="loop"
[[ -d "$BRIDGE" ]] || { echo "no secure-bridge/ at $BRIDGE"; exit 1; }

mkdir -p "$INBOX" "$OUTBOX" "$STATE"

# ---- parse args ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --once) MODE="once";;
    --push-outbox) MODE="push";;
    --daemon) MODE="daemon";;
    --interval) POLL="$2"; shift;;
    --log-file) LOG="$2"; shift;;
    *) ;;
  esac
  shift
done

log() { printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" | tee -a "$LOG"; }

# ---- one full pass: pull -> run new jobs -> capture logs -> push outbox ----
process_once() {
  log "=== pass start ==="
  cd "$REPO_ROOT"

  # 1) sync
  git pull --ff-only "$REMOTE" "$BRANCH" >/dev/null 2>&1 || \
    log "WARN: git pull failed (will retry on next loop)"

  # 2) run any NEW .py jobs (skip already-done ones via state/processed file)
  local handled=0
  for f in "$INBOX"/*.py; do
    [[ -f "$f" ]] || continue
    local base; base="$(basename "$f")"
    local donef="$STATE/${base}.done"
    [[ -f "$donef" ]] && continue
    log "running: $base"
    if python3 "$SCRIPT_DIR/runner.py" "$f" >>"$STATE/$base.stdout.log" 2>>"$STATE/$base.stderr.log"; then
      touch "$donef"
      log "  - ok: $base"
    else
      cp "$STATE/$base.stderr.log" "$OUTBOX/${base}.crash.txt" 2>/dev/null || true
      touch "$donef"   # prevent infinite re-run; crash log is outbound
      log "  - FAILED: $base (crash log added to outbox)"
    fi
    handled=1
  done

  # 3) push safe outbox back through PHI gate (even if no job ran, rotates logs)
  if [[ -z "$(find "$OUTBOX" -type f 2>/dev/null)" ]]; then
    log "outbox empty; skipping scan+push"
  elif "$SCRIPT_DIR/phi_scan.py" "$OUTBOX" >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && git add -A "$BRIDGE/bridge-outbox" && \
     git commit -q -m "bridge: outbound results" && \
     git push "$REMOTE" "$BRANCH") >/dev/null 2>&1 && \
       log "pushed outbox" || log "no outbox changes to push"
  else
    log "WARN: phi scan flagged outbox; refusing push"
  fi
  log "=== pass done (handled=$handled) ==="
}

mkdir -p "$STATE" "$OUTBOX" "$INBOX"

case "$MODE" in
  once)
    process_once ;;
  push)
    (cd "$REPO_ROOT" && git add -A "$BRIDGE/bridge-outbox" && \
     git commit -q -m "bridge: manual outbox push" && git push "$REMOTE" "$BRANCH") \
      >/dev/null 2>&1 && echo "pushed" || echo "nothing to push";
    ;;
  daemon)
    log "starting daemon (poll ${POLL}s)"
    nohup "$0" --interval "$POLL" --log-file "$LOG" </dev/null >>"$LOG" 2>&1 &
    disown
    echo "daemon pid: $!"
    ;;
  loop)
    log "listening on $INBOX (poll ${POLL}s)"
    while true; do
      process_once
      sleep "$POLL"
    done
    ;;
esac
