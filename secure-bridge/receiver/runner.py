#!/usr/bin/env python3
# ============================================================================
# RUNNER (secure server) — executes a job script in the live environment.
#
# Usage: python3 runner.py /path/to/job.py
#
# Captures stdout/stderr to files (handled by listener). Does NOT import user
# data, does NOT hold credentials, and never writes outside bridge-outbox/.
# ============================================================================
import importlib.util
import os
import sys
from pathlib import Path

def load_job(path: str):
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("bridge_job", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bridge_job"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # let listener log the traceback
        print(f"IMPORT ERROR: {e}", file=sys.stderr)
        sys.exit(3)
    if not hasattr(mod, "run_main"):
        print("job has no run_main()", file=sys.stderr)
        sys.exit(2)
    return mod

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: runner.py <job.py>", file=sys.stderr)
        sys.exit(1)
    job = load_job(sys.argv[1])
    try:
        rc = job.run_main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    # Keep stdout 100% job-owned on success: emit NOTHING to stderr. A running
    # cell's output is exactly the job's prints. Errors never reach stdout.
    sys.exit(0 if rc is None or rc == 0 else 1)
