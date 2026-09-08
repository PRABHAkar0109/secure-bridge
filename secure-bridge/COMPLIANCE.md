# Secure Bridge · Compliance & Certification Readiness

> **Read this first.** This document is an honest mapping of what the
> `secure-bridge` pipeline DOES enforce technically, and what is STILL
> required for a real HIPAA / SOC 2 / HITRUST certification. **This repo
> offers NO certification on its own** — certification is an external audit
> process, not software. Do not represent this as "certified" unless your
> organization's compliance team has formally attested it.

---

## What this pipeline enforces (technical controls)

| Control | Where | What it does |
|---|---|---|
| **Outbound PHI/secret DLP gate** | `receiver/phi_scan.py` | Policy-driven scanner (versioned `phi_policy.json`) blocks MRN/SSN/DOB/phone/email/insurance/token/secret/notebook patterns before anything leaves. Fail-closed. |
| **Inbound code-only rule** | `.gitignore` + `push_job.sh` + `runner.py` | Only plain `.py` enters; notebooks/raw data are refused. |
| **Aggregation discipline** | `template/job_template.py` + SOP | Jobs are instructed to print/write aggregates only; raw stdout never leaves. |
| **Quarantine** | `bridge-state/quarantine/<ts>/` | Blocked files are moved out of the outbox (not deleted, not pushed), so evidence is preserved. |
| **Audit trail** | `bridge-state/phi-audit.jsonl` | Every scan records timestamp, policy version, target, block/warn counts + classes, quarantine status — **without storing raw PHI**. |
| **Self-tests** | `receiver/phi_scan_test.py`, `phi_scan.py --self-test` | Automated fixtures prove detection of each identifier class and non-blocking of aggregates. |
| **Auto-show results** | extension | Raw cell-output transcripts only cross back if they pass the gate. |

---

## What certification ACTUALLY requires (not in this repo)

Real HIPAA (Security Rule) / SOC 2 / HITRUST certification is a **program**,
not a script. The organization must have:

1. **Signed BAs / policies** — Business Associate Agreements, privacy notices,
   incident response, workforce training, BAA with any cloud/lab vendor.
2. **Access control & IAM** — least-privilege identities, MFA, role-based
   access to the repo and the PHI server, separate PHI owner accounts.
3. **Encryption** — PHI **at rest** (encrypted volumes/db) and **in transit**
   (TLS ≥1.2 for every data path; the git bridge itself relies on the host's
   HTTPS/SSH transport).
4. **Certified / evaluated DLP & IRM** — organizations under audit typically
   require a **vendor DLP product** (e.g. Tessian, Nightfall, Google DLP,
   Microsoft Purview) and/or an IRM layer, not bespoke regex. This repo's
   scanner is a **best-effort control**, documented as such.
5. **De-identification standard** — HIPAA "Expert Determination" or Safe Harbor
   (removing all 18 identifiers) performed by/with your privacy officer before
   outbound use; a regex scanner is not a substitute.
6. **Logging & monitoring** — SIEM ingestion of the audit trail, alerting on
   PHI-block events, retention policy.
7. **Pen tests & risk assessment** — annual risk analysis, third-party
   penetration test of any PHI-hosting environment.
8. **Auditor evidence** — policy configuration reviews, access reviews,
   training records, and the DLP event history (which `phi-audit.jsonl`
   supports).

---

## Gap checklist (what to close before an audit)

- [ ] Get compliance team sign-off on this pipeline as an allowed PHI host.
- [ ] Replace or augment `phi_scan.py` with an org-approved vendor DLP that
      audits can cite.
- [ ] Ensure the PHI server has full-disk encryption and MFA'd least-privilege
      accounts; document it.
- [ ] Enforce TLS/HTTPS (or SSH) on the git bridge transport; disable plaintext.
- [ ] Write incident-response + data-retention policies for the bridge.
- [ ] Run `phi_scan_test.py` in CI so the gate's behavior is continuously proven.
- [ ] Have an expert-derivation/de-identification procedure for anything pushed
      outbound, not just regex gating.

---

## The honest bottom line

- **This repo gives you strong, auditable technical controls** and the evidence
  trail (policy version + audit log + self-tests) an assessor can review.
- **It is not, and cannot call itself, "HIPAA-certified."** Only your
  organization + a licensed assessor can grant certification.
- Treat `phi_scan.py` output as a **compliance-supporting control**, and pair
  it with the vendor DLP / de-identification / encryption items above.

*Owner of this statement: fill in your privacy/security officer. Review at
least annually and on every policy change (`phi_policy.json` carries a
`version` + `last_reviewed` you should bump).*
