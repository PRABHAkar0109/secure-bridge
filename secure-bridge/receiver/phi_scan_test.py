#!/usr/bin/env python3
# ============================================================================
# PHI SCANNER SELF-TEST / FIXTURE SUITE
#
# Auditable verification that the DLP gate detects the identifier classes it
# claims to, and does NOT false-positive on clean aggregate output. Run with:
#
#   python3 phi_scan_test.py                 # run all fixtures
#   python3 phi_scan_test.py -v              # verbose
#
# Exit 0 = all pass, 1 = a check failed.
# ============================================================================
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phi_scan  # noqa: E402

POLICY = Path(__file__).resolve().parent / "phi_policy.json"
POL = phi_scan.load_policy(POLICY)
RULES = POL["rules"]


def blocks(text):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "probe.txt"
        p.write_text(text)
        b, w, _ = phi_scan.scan_file(p, RULES)
        return b, w


class TestPhiBlocking(unittest.TestCase):
    def assert_has_block(self, text, cls):
        b, _ = blocks(text)
        self.assertTrue(any(x["class"] == cls for x in b),
                        f"expected block {cls} in {text!r}, got {b}")

    def assert_clean(self, text):
        b, _ = blocks(text)
        self.assertFalse(b, f"expected clean, got blocks {b}")

    # --- must BLOCK ---
    def test_mrn(self):
        self.assert_has_block("patient MRN = 12345678901 in row", "MRN")

    def test_ssn(self):
        self.assert_has_block("SSN 123-45-6789", "SSN")

    def test_dob(self):
        self.assert_has_block("born 1985-07-12", "DOB")

    def test_phone(self):
        self.assert_has_block("call (555) 123-4567", "PHONE")

    def test_email(self):
        self.assert_has_block("contact jane.doe@hosp.org", "EMAIL")

    def test_insurance_id(self):
        self.assert_has_block("member id ABC123456", "INSURANCE")

    def test_github_token(self):
        self.assert_has_block("tok = ghp_012345678901234567890123456789012345", "GITHUB_TOKEN")

    def test_secret(self):
        self.assert_has_block("password = hunter2", "SECRET")

    def test_forbidden_notebook(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.ipynb"
            p.write_text("{}")
            b, _, _ = phi_scan.scan_file(p, RULES)
            self.assertTrue(any(x["class"] == "FORBIDDEN_TYPE" for x in b))

    # --- must NOT block (aggregates) ---
    def test_clean_aggregate_table(self):
        self.assert_clean("# mean BP by age\n| 40-49 | 3 | 118.3 |\n| 50-59 | 2 | 131.5 |")

    def test_clean_mean(self):
        self.assert_clean("mean = 0.9982, n = 1042, p = 0.03")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
