# Secure Bridge · Standard Operating Procedure (SOP)

Once both loops are running you never need to look at the internal workspace
screen again. This page is the exact playbook, matching the original design.

> **TL;DR — "Code in, summaries out."** You write plain Python with your AI,
> the bridge pushes it inside, the secure server runs it against live data,
> and only scanned, aggregated results come back. Raw PHI never leaves.

---

## 0. The two loops you keep running

| Loop | Runs where | Command | Job |
|------|-----------|---------|-----|
| **Controller** | Your machine / Cursor terminal | `bash secure-bridge/sender/autosync.sh` | watches jobs + pulls reports |
| **Listener / Engine** | Secure server terminal | `./secure-bridge/receiver/listener.sh --daemon` | pulls jobs, runs them, pushes results |

Start both, verify once with `./secure-bridge/receiver/listener.sh --once`, then
let them run. On session restart, reschedule the listener via cron/login hook.

---

## 1. Prompt

In Cursor (or any code editor), tell your AI in plain language — English, Hindi,
or any native language. Example:

> "Find the mean blood pressure by age group from `/data/patients.json` and
> save a bar chart to `chart.png` and a summary table to `data_report.md`."

Or, the SOP equivalent for this bridge:

> "Fill `secure-bridge/template/job_template.py`: load the live BP data, group
> by age bucket, write the mean BP table to `bridge-outbox/data_report.md` and a
> bar chart to `bridge-outbox/chart.png`. **Aggregate only — never print raw
> identifiers.**"

## 2. Execute

1. Your AI writes/edits the job (`analysis.py`-style) and saves it to
   `secure-bridge/bridge-inbox/jobs/`.
2. `autosync.sh` on your machine picks up the change and pushes it.
3. `listener.sh` inside pulls it, and `receiver/runner.py` executes it against
   the secure, live environment.
4. The job writes safe results only to `secure-bridge/bridge-outbox/`.

## 3. Review — two displays, raw + summarized

Inside, the listener runs `receiver/phi_scan.py` over the outbox. Only files
that pass the scan are pushed back. On your machine, `autosync.sh` pulls them,
and you see the results in Cursor:

- **Raw cell output** → `bridge-outbox/<jobname>.transcript.txt` (the exact
  stdout the notebook showed — plain table, like an `Out[n]` frame)
- **Table / report** → `bridge-outbox/data_report.md` (rendered pretty)
- **Chart** → `bridge-outbox/chart.png` (inline preview)
- **Anything else** → `bridge-outbox/<jobname>.crash.txt` (see below)

If the Secure Bridge extension is loaded, the raw output also arrives
**automatically in chat** — see §4.5.

## 4. Fix — the auto re-run loop

If an internal execution fails:

1. A crash log arrives in Cursor as `bridge-outbox/<jobname>.crash.txt`.
2. Tell your AI: *"Check `<jobname>.crash.txt` and fix the job."*
3. Save the fixed job to the inbox again. The listener detects the change
   (per-file signature) and **auto re-runs it** on the next loop — no manual
   steps, no waiting on the server screen.
4. Successful jobs clear their stale crash log and push fresh
   `data_report.md` / `chart.png` back to you.

That loop — *write → crash → read → fix → auto re-run* — is the whole point:
the secure box stays headless.

---

## 4.5 Auto-show raw results — they arrive in chat, no asking

Every time the listener finishes a job it writes a **transcript of the exact
cell output** to the outbox:

- **`bridge-outbox/<jobname>.transcript.txt`** — the raw stdout of a single
  execution, byte-for-byte what the notebook cell shows (plain text, no
  markdown, no metadata up front). Bridge metadata is boxed below a
  `--- [bridge metadata] ---` line. This is **Display A** (what actually
  printed inside).

- **`bridge-outbox/data_report.md` / `chart.png`** — the pretty aggregated
  artifacts. This is **Display B** (what the AI summarizes for you).

The Secure Bridge Copilot extension watches the outbox and, the moment a new
`*.transcript.txt` lands, **delivers it into your chat automatically** as a
`📥 [secure-bridge]` message showing the raw cell output — plus pushes a live
update to the Secure Bridge dashboard and queues `pendingResults` on
`secure_bridge_status` as a fallback.

So the workflow is:

1. You ask (natural language): *"load patients, mean BP by age, chart it."*
2. The AI writes + pushes `analysis.py`; the inside listener runs it.
3. **Raw output arrives in your chat on its own** (`📥 ...`): the exact table
   the notebook printed.
4. The AI additionally gives you the concise summary / pretty chart.

No polling, no "check if it's done" — the result comes to you.

---

## 5. Guardrails that make this safe (don't "fix" these away)

- **Repo `.gitignore`**: raw data (`*.csv/xlsx/json/parquet...`, notebooks,
  pickles) is ignored repo-wide by default. **Exception**: everything the
  listener writes under `bridge-outbox/` is un-ignored because the PHI scan
  already passed it.
- **Outbound PHI gate** (`receiver/phi_scan.py`): blocks MRN/SSN/DOB/name/
  address/phone/secret patterns before any push out.
- **Only `bridge-outbox/` crosses back out.** Job stdout/stderr stays in
  local `bridge-state/` logs on the server.
- **Transcripts are PHI-scanned too.** `*.transcript.txt` (the raw cell
  output) rides the same outbound gate as everything else — raw identifiers
  in job output block the push, keeping the "clarity" feature from becoming a
  leak.
- **Inbox = execution sandbox.** Anyone with push rights can run code on the
  PHI server. Protect push access to the repo. (See also `wake_on_git.py` for
  a branch-review variant.)
- Fail-closed: if the PHI scan flags anything, nothing is pushed that pass.

---

## 6. Mapping to the original design

| Original idea | This implementation |
|---------------|---------------------|
| `analysis.py` at repo root | job file in `secure-bridge/bridge-inbox/jobs/` |
| `listener.py` (Python loop) | `receiver/listener.sh` (bash loop) + `runner.py` |
| `autosync.sh` on your machine | `sender/autosync.sh` |
| `error_log.txt` | `bridge-outbox/<jobname>.crash.txt` |
| `data_report.md`, `chart.png` | `bridge-outbox/` artifacts |
| `.gitignore` deny-raw-data | repo `.gitignore` + PHI scan double gate |

Everything your original pipeline did is here, plus: per-job isolation,
no-immediate-repeat on failure, content-signature re-runs on fix, and a
double guardrail so an accidental raw dump can't escape.

---

## 7. Troubleshooting

- **Job landed but never ran** → confirm it's in the server clone:
  `ls -la secure-bridge/bridge-inbox/jobs/`
- **Outbox file blocked** → manual scan for the reason:
  `python3 secure-bridge/receiver/phi_scan.py bridge-outbox/chart.png`
- **Listener stopped after a restart** → re-run with `--daemon`, or schedule
  `--once` on a login hook/cron.
- **Push conflict on your machine** → `autosync.sh` rebases and retries
  automatically; if it gave up, run `sender/push_job.sh <jobname>.py` once.
