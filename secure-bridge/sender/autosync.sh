#!/usr/bin/env bash
# ============================================================================
# AUTO-SYNC (run on YOUR machine, outside — the "Controller")
#
# Two-way background loop: pulls the internal results reports back into your
# editor, and pushes any new/changed JOB files you save in
# secure-bridge/bridge-inbox/jobs/ back up to the bridge.
#
#   ./secure-bridge/sender/autosync.sh                 # wrap up to date: md + png + txt
#   ./secure-bridge/sender/autosync.sh --interval 10   # half the time between pulls
#
# This is the Cursor-terminal counterpart of receiver/listener.sh. It never
# stages anything outside the bridge job + outbox paths, so raw data can't
# sneak back out. On a push conflict (e.g. listener pushed outbox while you
# were typing) it retries the push, never silently drops a job.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BRIDGE="$REPO_ROOT/secure-bridge"
INBOX="$BRIDGE/bridge-inbox/jobs"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
POLL=5
FAILED_PUSHES=0
MAX_FAILED_PUSHES=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) POLL="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

mkdir -p "$INBOX"

echo "[autosync] watching: $INBOX"
echo "[autosync] pulling results from $REMOTE/$BRANCH every ${POLL}s (Ctrl-C to stop)"

while true; do
  # 1) pull inbound results (md/png/txt in bridge-outbox) written by the listener
  git -C "$REPO_ROOT" pull --ff-only "$REMOTE" "$BRANCH" >/dev/null 2>&1 || \
    echo "[autosync] WARN: pull failed (network / server down?) — will retry"

  # 2) push any job file you saved locally (usually a new or edited analysis.py)
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$INBOX" "$BRIDGE/bridge-outbox")" ]]; then
    if git -C "$REPO_ROOT" add -A -- "$INBOX" "$BRIDGE/bridge-outbox" \
      && git -C "$REPO_ROOT" commit -q -m "bridge: autosync job update" \
      && git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
      echo "[autosync] pushed job/outbox changes"
      FAILED_PUSHES=0
    else
      # race with a concurrent listener push: pull-merge once, then re-push
      FAILED_PUSHES=$((FAILED_PUSHES + 1))
      git -C "$REPO_ROOT" pull --rebase --autostash "$REMOTE" "$BRANCH" >/dev/null 2>&1 || true
      if git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
        echo "[autosync] recovered after rebase"
        FAILED_PUSHES=0
      else
        echo "[autosync] WARN: push still failing ($FAILED_PUSHES/$MAX_FAILED_PUSHES)"
        if [[ "$FAILED_PUSHES" -ge "$MAX_FAILED_PUSHES" ]]; then
          echo "[autosync] ERROR: giving up until you run push_job.sh manually" >&2
          exit 1
        fi
      fi
    fi
  fi

  sleep "$POLL"
done
