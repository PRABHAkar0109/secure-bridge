# ============================================================================
# SECURE BRIDGE JOB TEMPLATE
# ----------------------------------------------------------------------------
# This is YOUR blank job. An AI (or a teammate) fills in a copy of this file
# and drops it into secure-bridge/bridge-inbox/jobs/. The server listener
# executes it against the live environment.
#
# COMPLIANCE RULES (read before writing anything):
#   1. NEVER import or run notebooks. Plain .py only.
#   2. NEVER print raw PHI (MRN, SSN, DOB, full names, addresses) to
#      stdout/stderr. Aggregate only (counts, means, distributions,
#      identifier-free tables).
#   3. NEVER write raw PHI to disk anywhere except under bridge-outbox/ —
#      and even there, run it through the PHI scanner before pushing.
#   4. Write ALL result files you want to return to your machine under
#      bridge-outbox/ (markdown, csv, png, txt crash logs). Nothing else
#      in the repo is pushed back.
# ============================================================================

import os
import sys
from pathlib import Path

# Paths. The JOB lives at  <repo>/secure-bridge/bridge-inbox/jobs/<name>.py
# so the repo root is 4 directories up from this file.
REPO_ROOT   = Path(__file__).resolve().parents[3]   # repo root (RFIs_and_Projects_Compendium/)
SECURE_DIR  = REPO_ROOT / "secure-bridge"
INBOX_DIR   = SECURE_DIR / "bridge-inbox"
OUTBOX_DIR  = SECURE_DIR / "bridge-outbox"

try:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:  # noqa: BLE001 - do not let setup failures hide errors
    print(f"ERROR: cannot create outbox dir: {e}", file=sys.stderr)
    sys.exit(1)


def run_main() -> None:
    """Placeholder. AI fills this with the actual analysis job.

    Examples this block produces (as safe, aggregated artifacts):
        - OUTBOX_DIR / "summary.md"
        - OUTBOX_DIR / "output.csv"
        - OUTBOX_DIR / "chart.png"
    """

    # ---- your code here ------------------------------------------------
    # e.g.
    #   import my_live_data_lib as live          # the protected environment
    #   df = live.load_latest_cohort()
    #   g  = (df.groupby("treatment_arm").agg(n=("patient_id", "nunique")))
    #   g.to_csv(OUTBOX_DIR / "tables" / "arms.csv")
    # --------------------------------------------------------------------
    print(f"No job logic yet. Write results to: {OUTBOX_DIR}")


if __name__ == "__main__":
    # Jobs may import from the live environment. Keep startup honest and
    # loud but PHI-safe.
    run_main()
