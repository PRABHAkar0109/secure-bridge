# Demo analysis job — PHI-SAFE synthetic data (no real identifiers).
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTBOX = REPO_ROOT / "secure-bridge" / "bridge-outbox"
OUTBOX.mkdir(parents=True, exist_ok=True)

def run_main():
    rows = [
        ("40-49", 118), ("40-49", 122), ("40-49", 115),
        ("50-59", 135), ("50-59", 128), ("60-69", 142), ("60-69", 138),
    ]
    groups = {}
    for age, bp in rows:
        groups.setdefault(age, []).append(bp)
    lines = ["# Demo blood-pressure summary (synthetic)", ""]
    lines.append("| age group | n | mean BP |")
    lines.append("|-----------|---|---------|")
    for age in sorted(groups):
        vals = groups[age]
        lines.append(f"| {age} | {len(vals)} | {sum(vals)/len(vals):.1f} |")
    (OUTBOX / "data_report.md").write_text("\n".join(lines) + "\n")
    print("Wrote:", OUTBOX / "data_report.md")
    return 0

if __name__ == "__main__":
    run_main()
