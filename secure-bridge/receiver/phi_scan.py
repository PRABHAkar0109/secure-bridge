#!/usr/bin/env python3
# ============================================================================
# SECURE BRIDGE PHI / SECRET DLP SCANNER (standards-oriented)
#
# Policy-driven outbound gate. Reads secure-bridge/receiver/phi_policy.json
# (versioned, auditable) and scans a file or directory for PHI/secret
# patterns. Fail-closed by default: any "block" finding refuses the push and
# (optionally) quarantines the file so nothing is silently lost.
#
# CLI (kept drop-in compatible with the legacy scanner):
#   python3 phi_scan.py <file-or-dir>                 # simple "PASSED/FAILED"
#   python3 phi_scan.py --json <file-or-dir>          # structured JSON report
#   python3 phi_scan.py self-test                     # built-in fixtures
#   python3 phi_scan.py --no-quarantine <file-or-dir>
#
# Exit codes: 0 = safe to push, 1 = blocked (fail-closed), 2 = usage error.
#
# NOTE: This is a best-effort DLP / audit layer. It is a technical control
# that HIPAA/SOC2/HITRUST audits evaluate — it is NOT itself a certification,
# and does NOT replace a certified DLP/IRM product, signed BAAs, or
# org-approved de-identification. See COMPLIANCE.md.
# ============================================================================
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_POLICY = Path(__file__).resolve().parent / "phi_policy.json"
RECEIVER_DIR = Path(__file__).resolve().parent
BRIDGE_STATE = Path(__file__).resolve().parents[1] / "bridge-state"  # .../secure-bridge/bridge-state


# --- policy loading ---------------------------------------------------------
def load_policy(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        pol = json.load(f)
    rules = []
    for name, spec in pol.get("identifier_classes", {}).items():
        sev = spec.get("severity", "warning")
        for pat in spec.get("patterns", []):
            rules.append({
                "class": name,
                "label": spec.get("label", name),
                "pattern": re.compile(pat, re.IGNORECASE),
                "severity": sev,
            })
    return {"meta": pol, "rules": rules}


FORBIDDEN_EXT = {".ipynb", ".pyc", ".pkl", ".joblib", ".pickle", ".h5", ".tiff", ".raw"}


def scan_file(path: Path, rules):
    blocks, warns = [], []
    meta = {}
    ext = path.suffix.lower()

    if ext in FORBIDDEN_EXT:
        blocks.append({"class": "FORBIDDEN_TYPE", "severity": "block",
                       "label": f"Rich/binary type {ext} may embed rendered PHI",
                       "hit": path.name})
        return blocks, warns, meta

    try:
        text = path.read_text(errors="replace")
    except Exception:
        blocks.append({"class": "UNREADABLE", "severity": "block",
                       "label": "Unreadable/binary", "hit": path.name})
        return blocks, warns, meta

    for r in rules:
        for m in r["pattern"].finditer(text):
            hit = m.group(0)
            rec = {"class": r["class"], "severity": r["severity"],
                   "label": r["label"], "hit": hit[:40]}
            if r["severity"] == "block":
                blocks.append(rec)
            elif len(hit) >= 4:
                warns.append(rec)
    meta = {"ext": ext, "bytes": len(text.encode("utf-8", "replace"))}
    return blocks, warns, meta


def scan_dir(path: Path, rules):
    blocks, warns, metas = [], [], []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            b, w, m = scan_file(child, rules)
            blocks += b
            warns += w
            if m:
                metas.append({"file": str(child.relative_to(path)), **m})
    return blocks, warns, {"file_count": len(metas), "files": metas}


# --- quarantine + audit -----------------------------------------------------
def quarantine(target: Path):
    """Move a flagged file into bridge-state/quarantine/<ts>/ (never pushed)."""
    try:
        qdir = BRIDGE_STATE / "quarantine" / time.strftime("%Y%m%d-%H%M%S")
        qdir.mkdir(parents=True, exist_ok=True)
        dest = qdir / target.name
        target.replace(dest)
        return str(dest)
    except Exception as e:
        return f"QUARANTINE_ERROR:{e}"


def append_audit(entry: dict):
    logpath = BRIDGE_STATE / "phi-audit.jsonl"
    try:
        logpath.parent.mkdir(parents=True, exist_ok=True)
        with open(logpath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # audit failure must never crash the gate


def builtin_self_test() -> bool:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ok.md").write_text("# BP summary\n| g | mean |\n|40-49|118.3|")
        (d / "bad.txt").write_text("MRN 1234567 Jane Doe dob 1980-01-02")
        pol = load_policy(DEFAULT_POLICY)
        b, w, _ = scan_file(d / "ok.md", pol["rules"])
        ok = ok and (not b)
        b2, w2, _ = scan_file(d / "bad.txt", pol["rules"])
        ok = ok and any(x["class"] in ("MRN", "DOB") for x in b2)
    return ok


def main(argv):
    ap = argparse.ArgumentParser(description="secure-bridge PHI/secret DLP gate")
    ap.add_argument("--json", action="store_true", help="emit structured JSON report")
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY, help="policy json path")
    ap.add_argument("--no-quarantine", action="store_true", help="do not move blocked files")
    ap.add_argument("--self-test", action="store_true", help="run built-in fixtures and exit")
    ap.add_argument("target", nargs="?", help="file or directory to scan")
    args = ap.parse_args(argv)

    if args.self_test:
        res = builtin_self_test()
        print("SELF TEST:", "PASS" if res else "FAIL")
        sys.exit(0 if res else 1)

    if not args.target:
        ap.error("target path required")

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"NO SUCH PATH: {target}", file=sys.stderr)
        sys.exit(2)

    pol = load_policy(args.policy)
    meta = pol["meta"]
    rules = pol["rules"]

    if target.is_dir():
        blocks, warns, scan_meta = scan_dir(target, rules)
    else:
        blocks, warns, scan_meta = scan_file(target, rules)

    scan_id = f"scan-{int(time.time())}"
    refused = bool(blocks)  # fail-closed: any block => refuse

    # quarantine a blocked FILE (move it out of outbox so it can't be pushed)
    quarantined = None
    if refused and meta.get("quarantine", True) and not args.no_quarantine and target.is_file():
        quarantined = quarantine(target)

    # audit record (no raw PHI in the log — counts + classes only)
    audit = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan_id": scan_id,
        "policy_id": meta.get("policy_id"),
        "target": str(target),
        "refused": refused,
        "block_count": len(blocks),
        "warn_count": len(warns),
        "block_classes": sorted({b["class"] for b in blocks}),
        "warn_classes": sorted({w["class"] for w in warns}),
        "quarantined": quarantined is not None,
        "quarantine_path": quarantined,
    }
    append_audit(audit)

    if args.json:
        print(json.dumps({
            "policy_id": meta.get("policy_id"),
            "policy_version": meta.get("version"),
            "scan_id": scan_id,
            "refused": refused,
            "block_count": len(blocks),
            "warn_count": len(warns),
            "findings": blocks + warns,
            "quarantined": quarantined,
            "audit_ts": audit["ts"],
        }, indent=2))
    else:
        if refused:
            print("PHI/secret scan REFUSED — content blocked from outbound push:")
            for b in blocks:
                print(f"  [BLOCK] {b['class']}: {b['label']} -> {b['hit']!r}")
            if quarantined:
                print(f"  Quarantined under: {quarantined}")
        elif warns:
            print("PHI/secret scan: PASSED with warnings (review recommended):")
            for w in warns:
                print(f"  [warn ] {w['class']}: {w['label']} -> {w['hit']!r}")
        else:
            print("PHI/secret scan: PASSED (no blocked content).")

    sys.exit(1 if refused else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
