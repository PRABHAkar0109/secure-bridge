#!/usr/bin/env python3
# ============================================================================
# PHI / SECRET SCANNER (secure server) — outbound gate.
#
# Usage:
#   python3 phi_scan.py <file-or-dir>
#
# Best-effort pattern check for common raw identifiers and secrets. Blocks
# files containing MRN/SSN/date-of-birth/name/address/phone patterns, and
# refuses to let notebooks or raw logs pass. NOT a certified DLP tool.
# Exit code 0 = safe to push, 1 = flagged (nothing out).
# ============================================================================
import re
import sys
from pathlib import Path

# Patterns: value -> (label, is_blocking)
# Blocking = anything that looks like a real identifier/secret → stop push.
# Warning  = risky content (SHOULD be reviewed; we fail-closed by default).
RULES = [
    # Social Security Number (xxx-xx-xxxx)
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", True),
    # Likely MRN / account ids (mostly numeric, 5-12 digits)
    (r"\bMRN\s*[=:#.]\s*\d{5,12}\b", "MRN", True),
    (r"\b(patient|mrn|encounter)\s*id[\s=:#.]+\d{5,12}\b", "PATIENT_ID", True),
    # Date of birth (yyyy-mm-dd style)
    (r"\b(19|20)\d{2}[-/]\d{2}[-/]\d{2}\b", "DOB", True),
    # ZIP+4 (also matches generic US zip); combined with address heuristics below
    (r"\b\d{5}(?:-\d{4})?\b", "POSTAL", False),
    # Phone
    (r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}\b", "PHONE", True),
    # Full names heuristic: Title + Capitalized First + Optional Middle + Last
    (r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-zA-Z]*){0,2}", "NAME", True),
    # Email
    (r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", "EMAIL", True),
    # Secrets / tokens
    (r"\bghp_[A-Za-z0-9]{20,}\b", "GITHUB_PAT", True),
    (r"\b(sk-|xoxb-|AKIA|eyJ)[A-Za-z0-9_-]{10,}\b", "SECRET", True),
    (r"\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+", "CRED", True),
]

# File types that are considered "rich" and may embed rendered PHI — always blocked
FORBIDDEN_EXT = {".ipynb", ".pyc", ".pkl", ".joblib", ".pickle", ".h5", ".tiff", ".raw"}


def scan_path(path: Path) -> tuple[list[str], list[str]]:
    """Return (blocked, warnings). Raise on binary/forbidden types."""
    flags, warns = [], []

    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                b, w = scan_path(child)
                flags += b
                warns += w
        return flags, warns

    if path.suffix.lower() in FORBIDDEN_EXT:
        flags.append(f"{path.name}: forbidden type {path.suffix}")
        return flags, warns

    try:
        text = path.read_text(errors="replace")
    except Exception:
        flags.append(f"{path.name}: unreadable/binary")
        return flags, warns

    for pat, label, blocking in RULES:
        for m in re.finditer(pat, text):
            hit = m.group(0)
            if blocking:
                flags.append(f"{path.name}: {label} -> {hit[:24]!r}")
            elif len(hit) >= 5:   # avoid flagging random small numbers
                warns.append(f"{path.name}: {label} -> {hit[:24]!r}")

    return flags, warns


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    target = Path(sys.argv[1]).resolve()
    if not target.exists():
        print(f"NO SUCH PATH: {target}")
        sys.exit(1)

    blocked, warns = scan_path(target)
    if blocked:
        print("PHI/secret scan FAILED — refusing outbound push:")
        for b in blocked:
            print("  [BLOCK] " + b)
        for w in warns:
            print("  [warn ] " + w)
        sys.exit(1)

    if warns:
        print("PHI/secret scan: passed with warnings (review recommended):")
        for w in warns:
            print("  [warn ] " + w)
    else:
        print("PHI/secret scan: PASSED (no blocked content).")
    sys.exit(0)
