#!/usr/bin/env bash
# ============================================================================
# SENDER (run on YOUR machine, outside the PHI perimeter)
# Sends a job to the bridge by pushing ONE file from inbound to origin.
#
#   ./secure-bridge/sender/push_job.sh path/to/job.py
#
# It stages ONLY the given file (never notebooks by default) and pushes to
# origin. Options:
#   --inbox PATH   override where the job lands server-side (default:
#                  secure-bridge/bridge-inbox/jobs/<basename>)
#   --allow-nb     allow a .ipynb to be pushed (NOT recommended: notebooks
#                  embed PHI)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-$(git -C "$REPO_ROOT" symbolic-ref --short -q HEAD 2>/dev/null || echo main)}"

ALLOW_NB="no"
INBOX_REL=""
JOB_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inbox)
      INBOX_REL="$2"; shift 2;;
    --allow-nb)
      ALLOW_NB="yes"; shift;;
    *)
      JOB_FILE="$1"; shift;;
  esac
done

if [[ -z "$JOB_FILE" ]]; then
  echo "usage: $0 [--inbox <rel/path>] [--allow-nb] path/to/job.py" >&2
  exit 2
fi

if [[ ! -f "$JOB_FILE" ]]; then
  echo "ERROR: file not found: $JOB_FILE" >&2
  exit 1
fi

if [[ "$JOB_FILE" == *.ipynb && "$ALLOW_NB" == "no" ]]; then
  echo "ERROR: refusing to send a .ipynb (notebooks embed rendered PHI)." >&2
  exit 1
fi

# default landing: secure-bridge/bridge-inbox/jobs/<basename>
DEST_REL="${INBOX_REL:-secure-bridge/bridge-inbox/jobs/$(basename "$JOB_FILE")}"
# normalize (strip leading ./)
DEST_REL="${DEST_REL#./}"

echo "Pushing '$JOB_FILE' -> $DEST_REL (@$REMOTE/$BRANCH)"

git -C "$REPO_ROOT" pull --ff-only "$REMOTE" "$BRANCH"

# copy into a tracked path so git sees it without churning unrelated dirs
mkdir -p "$(dirname "$REPO_ROOT/$DEST_REL")"
cp "$JOB_FILE" "$REPO_ROOT/$DEST_REL"
git -C "$REPO_ROOT" add -- "$DEST_REL"
git -C "$REPO_ROOT" commit -m "bridge: submit job $(basename "$JOB_FILE")" -q
git -C "$REPO_ROOT" push "$REMOTE" "$BRANCH"

echo "OK: job sent."
