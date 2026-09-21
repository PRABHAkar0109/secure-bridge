# ============================================================================
# SECURE BRIDGE JOB TEMPLATE  (schema-first workflow)
# ----------------------------------------------------------------------------
# Save a copy of this file to
# secure-bridge/bridge-inbox/jobs/<jobname>.py on YOUR machine, then either
# run `./secure-bridge/sender/push_job.sh <jobname>.py` once, or let
# autosync.sh pick it up. The secure listener executes it against the live
# environment.
#
# WHAT CROSSES THE BRIDGE (the whole point — read before writing):
#
#   OUTWARD (internal → you):
#     - data_schema.md        ← the data's SKELETON only (column names, row
#                               count, dtypes, source path). NO row values.
#     - *.error.txt           ← traceback, if the job failed. Always returned.
#
#   STAYS INTERNAL (never pushed back, by the listener's design):
#     - your analysis stdout, full results, values, charts — anything you
#       compute beyond the schema. View/verify these on the server.
#
# So the workflow is:
#   Phase 0 — send a probe job that writes ONLY the schema (column names /
#             field names / row counts / dtypes) to OUTBOX/data_schema.md.
#   Phase 1 — now that you can see the schema on your side, push the real
#             analysis code. It may compute whatever it wants INSIDE;
#             if it raises an error, the traceback comes back to you in
#             *.error.txt. Only the schema probe ever returns data layout.
#
# COMPLIANCE RULES:
#   1. Plain .py only. NEVER import or run notebooks — they embed PHI.
#   2. NEVER print raw PHI (MRN, SSN, DOB, full names, addresses) to stdout/
#      stderr. Use counts, means, distributions, identifier-free tables.
#   3. In Phase 0, write ONLY the schema skeleton to OUTBOX_DIR. In Phase 1,
#      write your results to local/state paths, NOT to the outbox, so values
#      never cross the gate.
# ============================================================================

import sys
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]   # repo root
OUTBOX_DIR = REPO_ROOT / "secure-bridge" / "bridge-outbox"
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def run_main() -> None:
    """Fill in the analysis.

    PHASE 0 (schema probe) — write ONLY the skeleton, e.g.:
        import pandas as pd
        df = pd.read_csv("/path/to/your/patients.csv")   # on the server
        lines = [
            "# Data schema",
            f"- rows: {len(df)}",
            "- columns:",
        ]
        lines += [f"  - {c}: {df[c].dtype}" for c in df.columns]
        (OUTBOX_DIR / "data_schema.md").write_text("\n".join(lines) + "\n")

    PHASE 1 (real analysis) — compute on the server; DO NOT write raw values
    to OUTBOX_DIR. If it fails, the traceback returns in *.error.txt.
    """
    # ---- your code here ------------------------------------------------
    print("No job logic yet. Schema probe writes data_schema.md; analysis "
          "stays internal; errors return in <job>.error.txt.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_main())
    except Exception as e:  # let the runner capture a clean traceback
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
