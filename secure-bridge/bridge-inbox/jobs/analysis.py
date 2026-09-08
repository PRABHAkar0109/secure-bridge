# Demo analysis job — PHI-SAFE synthetic data (no real identifiers).
# Mirrors what a notebook cell would PRINT, incl. the exact frame that Jupyter
# shows after execution ([Out 1:], no ANSI, plain text).
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

    # --- print exactly what a notebook cell would show, NO markdown ---
    print("mean_blood_pressure_by_age_group load = synthetic (7 rows)")
    print()
    print(f"{'age_group':<10}{'n':>4}  {'mean_bp':>8}")
    print("-" * 26)
    for age in sorted(groups):
        vals = groups[age]
        print(f"{age:<10}{len(vals):>4}  {sum(vals)/len(vals):>8.1f}")
    print()

    # --- also persist the result artifact (what we already do) ---
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
