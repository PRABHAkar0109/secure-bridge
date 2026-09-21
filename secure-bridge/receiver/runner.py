#!/usr/bin/env python3
# ============================================================================
# RUNNER (secure workspace) — executes one job script in the live environment.
#
#   python3 runner.py /path/to/job.py
#
# Loads the job's run_main() and runs it. stdout/stderr are captured by the
# listener. The job never receives credentials; it only writes to
# bridge-outbox/, which the PHI gate scans before anything is pushed back.
# ============================================================================
import importlib.util
import sys
import traceback
from pathlib import Path


def main(argv):
    if len(argv) < 2:
        print("usage: runner.py <job.py>", file=sys.stderr)
        return 1
    path = Path(argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("bridge_job", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bridge_job"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        print(f"IMPORT ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3
    if not hasattr(mod, "run_main"):
        print("job has no run_main()", file=sys.stderr)
        return 2
    try:
        rc = mod.run_main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0 if rc is None or rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
