#!/usr/bin/env python3
# ============================================================================
# BRIDGE SMOKE TEST  (safe — no PHI)
# Drop a copy of this into  secure-bridge/bridge-inbox/jobs/  on your machine,
# send it with the sender, and the secure-server listener will run it and push
# the (safe) results back. It only writes aggregate info, never patient data.
# ============================================================================
import platform
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTBOX = REPO_ROOT / "secure-bridge" / "bridge-outbox"
OUTBOX.mkdir(parents=True, exist_ok=True)


def run_main() -> None:
    lines = []
    lines.append("# Bridge smoke test — it worked!")
    lines.append("")
    lines.append(f"- Host: {socket.gethostname() or 'unknown'}")
    lines.append(f"- Platform: {platform.platform()}")
    lines.append(f"- Python: {sys.version.split()[0]}")
    lines.append(f"- Repo root: {REPO_ROOT}")
    lines.append("")

    # Optional: probe the data mount WITHOUT reading identifiers.
    # e.g. if your live data lives at /shared/data, a count is safe:
    # data_dir = Path("/shared/data")
    # if data_dir.exists():
    #     lines.append(f"- Data dir exists: {data_dir} (files: {len(list(data_dir.rglob('*'))[:100])}+)")

    report = "\n".join(lines)
    (OUTBOX / "smoke_test.md").write_text(report)
    print("smoke test wrote:", OUTBOX / "smoke_test.md")
    print(report)


if __name__ == "__main__":
    run_main()
