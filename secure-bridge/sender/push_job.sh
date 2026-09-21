#!/usr/bin/env bash
# ============================================================================
# SENDER / PUSH JOB (run on YOUR machine, outside the secure workspace)
#
# Sends ONE plain-Python job file through the bridge: copies it into
# secure-bridge/bridge-inbox/jobs/ and pushes it to origin, so the secure
# listener will run it against the live data.
#
#   ./secure-bridge/sender/push_job.sh path/to/job.py
#
# --- external workspace one-time setup (from your machine's clone) ---
#   cp secure-bridge/sender/.env.example secure-bridge/sender/.env
#   # fill in GIT_REMOTE / GIT_BRANCH (use a fine-grained repo-limited PAT)
#   chmod +x secure-bridge/sender/*.sh
#   ./secure-bridge/sender/push_job.sh myjob.py
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# optional env overrides (from sender/.env if present)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
fi
REMOTE="${REMOTE:-${GIT_REMOTE:-origin}}"
BRANCH="${BRANCH:-${GIT_BRANCH:-$(git -C "$REPO_ROOT" symbolic-ref --short -q HEAD 2>/dev/null || echo main)}}"
INBOX_REL=""
ALLOW_NB="no"
JOB_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inbox)   INBOX_REL="$2"; shift 2;;
    --allow-nb) ALLOW_NB="yes"; shift;;
    *) JOB_FILE="$1"; shift;;
  esac
done

if [[ -z "$JOB_FILE" ]]; then
  echo "usage: $0 [--inbox <rel/path>] [--allow-nb] path/to/job.py" >&2
  exit 2
fi
[[ -f "$JOB_FILE" ]] || { echo "ERROR: file not found: $JOB_FILE" >&2; exit 1; }
if [[ "$JOB_FILE" == *.ipynb && "$ALLOW_NB" != "yes" ]]; then
  echo "ERROR: refusing to send a .ipynb (notebooks embed rendered PHI)." >&2
  exit 1
fi

DEST_REL="${INBOX_REL:-secure-bridge/bridge-inbox/jobs/$(basename "$JOB_FILE")}"
DEST_REL="${DEST_REL#./}"

echo "Pushing '$JOB_FILE' -> $DEST_REL (@$REMOTE/$BRANCH)"
git -C "$REPO_ROOT" pull --ff-only "$REMOTE" "$BRANCH"

mkdir -p "$REPO_ROOT/$(dirname "$DEST_REL")"
cp "$JOB_FILE" "$REPO_ROOT/$DEST_REL"
git -C "$REPO_ROOT" add -- "$DEST_REL"
git -C "$REPO_ROOT" commit -q -m "bridge: submit job $(basename "$JOB_FILE")"
git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH"
echo "OK: job sent."
