#!/usr/bin/env bash
# ============================================================================
# SENDER / AUTO-SYNC (run on YOUR machine, outside the secure workspace)
#
# Two-way background loop: pulls results back from the outbox into your editor
# and pushes any NEW or EDITED job files you save under
# secure-bridge/bridge-inbox/jobs/ back to the bridge.
#
#   bash secure-bridge/sender/autosync.sh                 # polls every 5s
#   bash secure-bridge/sender/autosync.sh --interval 10   # slower polling
#
# --- external workspace one-time setup (from your machine's clone) ---
#   cp secure-bridge/sender/.env.example secure-bridge/sender/.env
#   # fill in GIT_REMOTE / GIT_BRANCH
#   bash secure-bridge/sender/autosync.sh        # keep this terminal open
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BRIDGE="$REPO_ROOT/secure-bridge"
INBOX="$BRIDGE/bridge-inbox/jobs"
OUTBOX="$BRIDGE/bridge-outbox"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
fi
REMOTE="${REMOTE:-${GIT_REMOTE:-origin}}"
BRANCH="${BRANCH:-${GIT_BRANCH:-main}}"
POLL=5
FAILED_PUSHES=0
MAX_FAILED_PUSHES=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) POLL="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

mkdir -p "$INBOX" "$OUTBOX"
echo "[autosync] watching: $INBOX"
echo "[autosync] pulling results from $REMOTE/$BRANCH every ${POLL}s (Ctrl-C to stop)"

while true; do
  # 1) pull results the secure listener pushed back
  git -C "$REPO_ROOT" pull --ff-only "$REMOTE" "$BRANCH" >/dev/null 2>&1 || \
    echo "[autosync] WARN: pull failed (network / server down?) — retrying"

  # 2) push any job you saved locally (new or edited analysis.py)
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$INBOX" "$OUTBOX")" ]]; then
    if git -C "$REPO_ROOT" add -A -- "$INBOX" "$OUTBOX" \
      && git -C "$REPO_ROOT" commit -q -m "bridge: autosync job update" \
      && git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
      echo "[autosync] pushed job/outbox changes"
      FAILED_PUSHES=0
    else
      # race with a concurrent listener push: rebase once, then re-push
      FAILED_PUSHES=$((FAILED_PUSHES + 1))
      git -C "$REPO_ROOT" pull --rebase --autostash "$REMOTE" "$BRANCH" >/dev/null 2>&1 || true
      if git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
        echo "[autosync] recovered after rebase"
        FAILED_PUSHES=0
      else
        echo "[autosync] WARN: push still failing ($FAILED_PUSHES/$MAX_FAILED_PUSHES)"
        if [[ "$FAILED_PUSHES" -ge "$MAX_FAILED_PUSHES" ]]; then
          echo "[autosync] ERROR: giving up — run push_job.sh manually" >&2
          exit 1
        fi
      fi
    fi
  fi

  sleep "$POLL"
done
