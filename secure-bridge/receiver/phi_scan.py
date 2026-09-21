#!/usr/bin/env python3
# ============================================================================
# PHI / SECRET SCANNER — outbound gate for secure-bridge.
#
# Scans a file or directory for raw identifiers (MRN/SSN/DOB/phone/email/
# names/addresses/tokens/secrets) before anything is allowed to leave the
# secure workspace. Fail-closed: any block => refuse the push.
#
#   python3 phi_scan.py <file-or-dir>      # prints PASSED / REFUSED
#   python3 phi_scan.py --json <path>      # machine-readable report
#   python3 phi_scan.py --self-test        # verify the gate itself works
#
# Exit: 0 = safe to push, 1 = blocked, 2 = usage error.
#
# NOTE: best-effort pattern control, not certified DLP. Raw PHI should be
# kept inside the workspace; treat this gate as a guardrail, not a guarantee.
# ============================================================================
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

# --- identifier patterns -----------------------------------------------------
# (class, severity, regex, human label)
RULES = [
    ("MRN",        "block",   r"\bMRN\s*[=:#. ]+\d{5,12}",
     "Medical Record Number"),
    ("SSN",        "block",   r"\b\d{3}-\d{2}-\d{4}\b",
     "Social Security Number"),
    ("DOB",        "block",   r"\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b",
     "Date of Birth"),
    ("PHONE",      "block",   r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}",
     "Phone Number"),
    ("EMAIL",      "block",   r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}",
     "Email Address"),
    ("INSURANCE",  "block",   r"(?:member|policy|insurance|claim)\s+(?:id|no|number|#)\s*[:=#. ]+[A-Z0-9]{6,}",
     "Insurance / Member ID"),
    ("GITHUB_TOKEN", "block", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
     "GitHub Token"),
    ("SECRET",     "block",   r"\b(?:sk-|xoxb-|AKIA|eyJ)[A-Za-z0-9_-]{10,}\b|\b(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+",
     "Secret / Token"),
    ("NAME",       "warn",    r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Miss|Prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-zA-Z]*){0,2}",
     "Person Name (heuristic)"),
    ("POSTAL",     "warn",    r"\b\d{5}(?:[- ]?\d{4})?\b",
     "US ZIP / Postal"),
]

FORBIDDEN_EXT = {".ipynb", ".pyc", ".pkl", ".joblib", ".pickle", ".h5", ".tiff", ".raw"}
COMPILED = [(cls, sev, re.compile(p, re.IGNORECASE), label) for cls, sev, p, label in RULES]
BRIDGE_STATE = Path(__file__).resolve().parents[1] / "bridge-state"


def scan_file(path: Path):
    blocks, warns = [], []
    if path.suffix.lower() in FORBIDDEN_EXT:
        return [{"class": "FORBIDDEN_TYPE", "severity": "block",
                 "label": "Rich/binary type may embed rendered PHI", "hit": path.name}], warns
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return [{"class": "UNREADABLE", "severity": "block", "label": "Unreadable/binary",
                 "hit": path.name}], warns
    for cls, sev, rx, label in COMPILED:
        for m in rx.finditer(text):
            rec = {"class": cls, "severity": sev, "label": label, "hit": m.group(0)[:40]}
            (blocks if sev == "block" else warns).append(rec)
    return blocks, warns


def scan_dir(path: Path):
    blocks, warns, count, blocked_files = [], [], 0, set()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            count += 1
            b, w = scan_file(child)
            if b:
                blocked_files.add(child)
            blocks += b
            warns += w
    return blocks, warns, count, blocked_files


def quarantine(target: Path):
    try:
        qdir = BRIDGE_STATE / "quarantine" / time.strftime("%Y%m%d-%H%M%S")
        qdir.mkdir(parents=True, exist_ok=True)
        dest = qdir / target.name
        target.replace(dest)
        return str(dest)
    except Exception as e:  # never let quarantine failure hide the block
        return f"QUARANTINE_ERROR:{e}"


def append_audit(entry: dict):
    try:
        BRIDGE_STATE.mkdir(parents=True, exist_ok=True)
        with open(BRIDGE_STATE / "phi-audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # audit failure must never crash the gate


def self_test() -> bool:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ok.md").write_text("# BP summary\n|40-49|3|118.3|")
        (d / "bad.txt").write_text("MRN 12345678901 dob 1985-07-12")
        b1, _ = scan_file(d / "ok.md")
        ok = ok and not b1
        b2, _ = scan_file(d / "bad.txt")
        ok = ok and any(r["class"] in ("MRN", "DOB") for r in b2)
    return ok


def main(argv):
    ap = argparse.ArgumentParser(description="secure-bridge PHI/secret gate")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--no-quarantine", action="store_true")
    ap.add_argument("target", nargs="?")
    args = ap.parse_args(argv)

    if args.self_test:
        res = self_test()
        print("SELF TEST:", "PASS" if res else "FAIL")
        sys.exit(0 if res else 1)

    if not args.target:
        ap.error("target path required")
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"NO SUCH PATH: {target}", file=sys.stderr)
        sys.exit(2)

    quarantined = None
    if target.is_dir():
        blocks, warns, count, blocked_files = scan_dir(target)
        # fail-closed: any block refuses the push. Move every blocked FILE out
        # of the outbox so one bad artifact can't wedge the whole pipeline
        # (safe files still go through on the next pass).
        refused = bool(blocks)
        if refused and not args.no_quarantine:
            for bf in sorted(blocked_files):
                q = quarantine(bf)
                if q:
                    quarantined = q
    else:
        blocks, warns = scan_file(target)
        count = 1
        refused = bool(blocks)
        # a blocked FILE is moved out of the outbox so it can never be staged
        if refused and not args.no_quarantine:
            quarantined = quarantine(target)

    # audit record — counts/classes only, never the raw value
    append_audit({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": str(target),
        "refused": refused,
        "block_classes": sorted({b["class"] for b in blocks}),
        "warn_classes": sorted({w["class"] for w in warns}),
        "quarantined": quarantined is not None,
    })

    if args.json:
        print(json.dumps({"refused": refused, "block_count": len(blocks),
                          "warn_count": len(warns), "files": count,
                          "findings": blocks + warns, "quarantined": quarantined}, indent=2))
    elif refused:
        print("PHI scan REFUSED — content blocked from outbound push:")
        for b in blocks:
            print(f"  [BLOCK] {b['class']}: {b['label']} -> {b['hit']!r}")
        if quarantined:
            print(f"  Quarantined under: {quarantined}")
    elif warns:
        print("PHI scan PASSED (review warnings):")
        for w in warns:
            print(f"  [warn ] {w['class']}: {w['label']} -> {w['hit']!r}")
    else:
        print("PHI scan PASSED (no blocked content).")
    sys.exit(1 if refused else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
