#!/usr/bin/env bash
# ============================================================================
# RECEIVER / LISTENER (run on the SECURE workspace only)
#
# Pulls new/edited jobs from the inbox, runs them, and pushes back ONLY
# results that pass the PHI gate from the outbox.
#
#   ./secure-bridge/receiver/listener.sh             # loop (default 20s)
#   ./secure-bridge/receiver/listener.sh --once      # single pass
#   ./secure-bridge/receiver/listener.sh --daemon    # background (nohup)
#
# --- internal workspace one-time setup (from the secure workspace root) ---
#   chmod +x secure-bridge/receiver/*.sh secure-bridge/receiver/*.py
#   ./secure-bridge/receiver/listener.sh --daemon
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
BRANCH="${BRANCH:-$(git -C "$REPO_ROOT" symbolic-ref --short -q HEAD 2>/dev/null || echo main)}"
MODE="loop"
STAMP="$(date +%s)"   # one marker per process; not persisted

[[ -d "$BRIDGE" ]] || { echo "no secure-bridge/ at $BRIDGE" >&2; exit 1; }
mkdir -p "$INBOX" "$OUTBOX" "$STATE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)      MODE="once";;
    --push-outbox) MODE="push";;
    --daemon)    MODE="daemon";;
    --interval)  POLL="$2"; shift;;
    --log-file)  LOG="$2"; shift;;
    *) ;;
  esac
  shift
done

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

# ---- zero-risk guard: refuse to start if the gate itself is broken ---------
if ! python3 "$SCRIPT_DIR/phi_scan.py" --self-test >/dev/null 2>&1; then
  log "FATAL: PHI scanner self-test FAILED; refusing to start listener"
  exit 1
fi

# ============================================================================
# new_jobs: print jobs that are NEW or CHANGED since the last run
# ============================================================================
new_jobs() {
  local f base sigf sig
  for f in "$INBOX"/*.py; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    sigf="$STATE/${base}.sig"
    sig="$(cksum "$f" | awk '{print $1}')"
    if [[ -n "$sig" ]] && [[ -f "$sigf" ]] && [[ "$sig" == "$(cat "$sigf")" ]]; then
      continue
    fi
    printf '%s\n' "$f"
  done
}

# ============================================================================
# run_job: execute one job; push back ONLY schema + errors, never data values
# ============================================================================
run_job() {
  local f="$1" base sig sigf runout runerr rc
  base="$(basename "$f")"
  sig="$(cksum "$f" | awk '{print $1}')"
  sigf="$STATE/${base}.sig"
  runout="$STATE/${base}.${STAMP}.out"
  runerr="$STATE/${base}.${STAMP}.err"

  log "running: $base"
  python3 "$SCRIPT_DIR/runner.py" "$f" >"$runout" 2>"$runerr"
  rc=$?

  if [[ $rc -eq 0 ]]; then
    rm -f "$OUTBOX/${base}.error.txt"
    [[ -n "$sig" ]] && printf '%s' "$sig" >"$sigf"
    log "  - ok: $base"
  else
    # propagate the error/traceback to the external side (always allowed)
    { echo "ERROR running $base (exit $rc):"; echo; cat "$runerr"; } \
      > "$OUTBOX/${base}.error.txt" 2>/dev/null || true
    [[ -n "$sig" ]] && printf '%s' "$sig" >"$sigf"
    log "  - FAILED: $base (error log in outbox)"
  fi

  # keep server-side history logs (never pushed)
  cat "$runout" >> "$STATE/$base.stdout.log" 2>/dev/null || true
  cat "$runerr" >> "$STATE/$base.stderr.log" 2>/dev/null || true
}

# ============================================================================
# process_once: one full pass — pull / run new jobs / push safe outbox
# ============================================================================
process_once() {
  log "=== pass start ==="
  cd "$REPO_ROOT"

  # 1) pull anything the external side pushed in
  git pull --ff-only "$REMOTE" "$BRANCH" >/dev/null 2>&1 || \
    log "WARN: git pull failed (will retry on next loop)"

  # 2) run new/changed jobs
  local f handled=0
  if [[ -d "$INBOX" ]]; then
    while IFS= read -r f; do
      [[ -f "$f" ]] && run_job "$f" && handled=1
    done < <(new_jobs || true)
  fi

  # 3) push the outbox back ONLY if every file passes the PHI gate
  if [[ -z "$(find "$OUTBOX" -type f 2>/dev/null)" ]]; then
    log "outbox empty; nothing to push"
  elif python3 "$SCRIPT_DIR/phi_scan.py" "$OUTBOX" >/dev/null 2>&1; then
    git add -A "$BRIDGE/bridge-outbox"
    if git diff --cached --quiet; then
      log "outbox unchanged; nothing to push"
    else
      git commit -q -m "bridge: outbound results" && \
        git push "$REMOTE" "$BRANCH" >/dev/null 2>&1 && \
        log "pushed outbox" || log "WARN: outbox push failed"
    fi
  else
    log "WARN: phi scan flagged outbox; refusing push"
  fi
  log "=== pass done (handled=$handled) ==="
}

case "$MODE" in
  once)  process_once ;;
  push)
    (cd "$REPO_ROOT" && git add -A "$BRIDGE/bridge-outbox" && \
     git commit -q -m "bridge: manual outbox push" && git push "$REMOTE" "$BRANCH") \
      >/dev/null 2>&1 && echo "pushed" || echo "nothing to push" ;;
  daemon)
    log "starting daemon (poll ${POLL}s)"
    nohup "$0" --interval "$POLL" --log-file "$LOG" </dev/null >>"$LOG" 2>&1 &
    disown
    echo "daemon pid: $!" ;;
  loop)
    log "listening on $INBOX (poll ${POLL}s)"
    while true; do
      process_once
      sleep "$POLL"
    done ;;
esac
