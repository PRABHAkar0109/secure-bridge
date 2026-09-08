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

  # 2) run any NEW or CHANGED .py jobs. Signature check lets an edit in
  #    Cursor (a "fix" to analysis.py) auto re-run it on the next loop; a
  #    crash log is written to the outbox every failure so you can read it.
  local handled=0
  for f in "$INBOX"/*.py; do
    [[ -f "$f" ]] || continue
    local base; base="$(basename "$f")"
    local sig; sig="$(md5sum "$f" 2>/dev/null | cut -d' ' -f1)"
    local sigf="$STATE/${base}.sig"
    [[ -n "$sig" ]] && [[ -f "$sigf" ]] && [[ "$sig" == "$(cat "$sigf" 2>/dev/null)" ]] && continue
    log "running: $base"
    # Per-run stdout/stderr for the transcript ONLY — the job's output for a
    # single execution, exactly like a notebook cell renders it (we do NOT use
    # the accumulating .stdout.log which grows across runs).
    local runout="$STATE/${base}.run.out"; : > "$runout"
    local runerr="$STATE/${base}.run.err"; : > "$runerr"
    if python3 "$SCRIPT_DIR/runner.py" "$f" >>"$runout" 2>>"$runerr"; then
      rm -f "$OUTBOX/${base}.crash.txt" 2>/dev/null || true
      [[ -n "$sig" ]] && printf '%s' "$sig" >"$sigf"
      log "  - ok: $base"
    else
      cp "$runerr" "$OUTBOX/${base}.crash.txt" 2>/dev/null || true
      [[ -n "$sig" ]] && printf '%s' "$sig" >"$sigf"   # record sig; re-run only on edit
      log "  - FAILED: $base (crash log added to outbox)"
    fi
    # 2b) assemble the FULL execution transcript: RAW cell output first
    #     (exactly as Jupyter shows it), then clearly-separated bridge metadata.
    log "  - writing transcript: $base.transcript.txt"
    {
      # ---- RAW CELL OUTPUT (what the notebook displays after execution) ----
      cat "$runout" 2>/dev/null
      # stderr appended verbatim too — matches a terminal/notebook merged view
      # (e.g. a traceback, which the cell shows in red).
      if [[ -s "$runerr" ]]; then
        echo ""
        echo "--- stderr (as shown in the cell) ---"
        cat "$runerr" 2>/dev/null
      fi
      # ---- BRIDGE METADATA (clearly separated from the cell output) ----
      echo ""
      echo ""
      echo "--- [bridge metadata] ---"
      echo "job: $base | runner exit: $(if [[ -f "$OUTBOX/${base}.crash.txt" ]]; then echo FAILED; else echo SUCCESS; fi)"
      echo "transcript generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "stdout(per-run): $runout"
      echo "stderr(per-run): $runerr"
    } > "$OUTBOX/${base}.transcript.txt"
    # keep the aggregate history logs too (for server-side debugging)
    cat "$runout" >> "$STATE/$base.stdout.log" 2>/dev/null || true
    cat "$runerr" >> "$STATE/$base.stderr.log" 2>/dev/null || true
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
