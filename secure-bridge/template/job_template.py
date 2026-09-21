# ============================================================================
# SECURE BRIDGE JOB TEMPLATE
# ----------------------------------------------------------------------------
# Copy this file (or edit it) and save it to
# secure-bridge/bridge-inbox/jobs/<jobname>.py on YOUR machine, then either
# run `./secure-bridge/sender/push_job.sh <jobname>.py` once, or let
# autosync.sh pick it up. The secure listener executes it against the live
# environment and pushes safe results back.
#
# COMPLIANCE RULES (read before writing anything):
#   1. Plain .py only. NEVER import or run notebooks — they embed PHI.
#   2. NEVER print raw PHI (MRN, SSN, DOB, full names, addresses) to
#      stdout/stderr. Aggregate only (counts, means, identifier-free tables).
#   3. Write ONLY the result files you want returned to your machine under
#      bridge-outbox/. Everything there is PHI-scanned before it can leave.
#      Never write raw data anywhere else in this repo.
# ============================================================================

import sys
from pathlib import Path

# Paths. The job lives at  <repo>/secure-bridge/bridge-inbox/jobs/<name>.py
# so the repo root is 3 directories up from this file.
REPO_ROOT  = Path(__file__).resolve().parents[3]   # repo root
OUTBOX_DIR = REPO_ROOT / "secure-bridge" / "bridge-outbox"

OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def run_main() -> None:
    """Placeholder — fill in the actual analysis.

    Safe examples this block produces as artifacts:
        - OUTBOX_DIR / "summary.md"   (aggregate table)
        - OUTBOX_DIR / "output.csv"   (aggregates only)
        - OUTBOX_DIR / "chart.png"
    """
    # ---- your code here ------------------------------------------------
    # e.g.
    #   df = live.load_latest_cohort()            # the protected environment
    #   g  = df.groupby("treatment_arm").agg(n=("patient_id", "nunique"))
    #   g.to_csv(OUTBOX_DIR / "tables" / "arms.csv")
    # --------------------------------------------------------------------
    print(f"No job logic yet. Write results to: {OUTBOX_DIR}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_main())
    except Exception as e:  # let the runner capture a clean traceback
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
