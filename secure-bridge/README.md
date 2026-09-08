# Secure Bridge · Git-based "code in / results out" for protected workspaces

A headless, terminal-based Git loop that lets you author **plain Python
scripts** outside a locked-down, PHI-protected Jupyter environment (e.g. with
an AI assistant like Cursor), push them to a shared repo, and have a listener
on the secure server pull + execute them against live health records — pushing
**only safe, summarized outputs** back out.

> **The rule that keeps you compliant:**
> - **In-bound** — only plain `.py` code crosses in. **No notebooks, ever**:
>   notebooks silently embed rendered PHI (dataframes, error traces, plots) in
>   hidden metadata.
> - **Out-bound** — only files written under `bridge-outbox/` are pushed back,
>   passed through a PHI-scanner that blocks raw identifiers
>   (MRN/SSN/DOB/name/address patterns). Raw data never leaves the server.

---

## Layout

```
secure-bridge/
├── README.md               <- this file
├── SOP.md                  <- standard operating procedure (write→run→review→fix)
├── template/
│   └── job_template.py     <- your "blank job" for the AI to fill
├── sender/
│   ├── autosync.sh         <- run on YOUR machine (outside); background 2-way loop
│   ├── push_job.sh         <- run on YOUR machine (outside) to send a job once
│   └── .env.example        <- PAT/remote template (NEVER commit real token)
└── receiver/
    ├── listener.sh         <- run on the SECURE server (inside); pull+run+push
    ├── runner.py           <- executes a job, captures stdout/stderr
    ├── phi_scan.py         <- PHI/secret scanner gate for outbound files
    └── wake_on_git.py      <- (off by default) git-change-triggered loop
```

> **Interactive control panel + auto-show (Copilot extension):** this repo
> ships a project Copilot extension at `.github/extensions/secure-bridge/` —
> an interactive dashboard (list inbox / outbox, run PHI scan, read reports,
> send jobs), agent tools like `secure_bridge_send_job`, and an **auto-notify
> watcher** that delivers each new inside execution result (`*.transcript.txt`)
> straight into your chat as a `📥 [secure-bridge]` message with the raw
> notebook-style cell output. See `.github/extensions/secure-bridge/` and
> `SOP.md §4.5`.


On first run the receiver creates its working subfolders **inside its own
clone only**:

```
RFIs_and_Projects_Compendium/
└── secure-bridge/
    ├── bridge-inbox/jobs/  <- where you drop new job .py files (pushed in)
    ├── bridge-outbox/      <- where safe results are written (pushed back)
    └── bridge-state/       <- local run state (logs, since-markers; NOT pushed)
```
No other folder in your shared directory is ever touched.

---

## How it works

1. **You (outside)** ask your AI to fill `template/job_template.py` and save
   it to `secure-bridge/bridge-inbox/jobs/<jobname>.py` (on your machine).
2. You run `sender/push_job.sh <jobname>.py` → it stages **only** that file
   and `git push`es it.
3. Inside your clone, the listener runs: it `git pull`s and looks for new
   files in `bridge-inbox/jobs/`.
4. `receiver/runner.py` executes each new job's `run_main()` with the live
   environment; the job may write results **only** into `bridge-outbox/`.
5. Anything in `bridge-outbox/` is scanned by `receiver/phi_scan.py`
   (MRN/SSN/DOB/name/address/secret patterns). Only passing files get
   `git add`ed and pushed back.
6. **You (outside)** `git pull` and review aggregated tables/charts + crash
   logs in Cursor. PHI stays inside.

---

## Setup

### A. On the secure server (inside)

```bash
cd /shared/team-folder/RFIs_and_Projects_Compendium   # your clone
# make the receiver executable
chmod +x secure-bridge/receiver/*.sh secure-bridge/receiver/*.py
# run the listener in the background (keep this terminal open, or use nohup):
./secure-bridge/receiver/listener.sh --daemon
```

`--daemon` runs `listener.sh` with `nohup` so it keeps going if you close the
terminal. **Note:** background gates may be reset when the server/session
restarts — schedule `listener.sh --once` via cron or a login hook to keep it
alive, and keep going with a `--interval` loop (default 20s) for live inbound.

### B. On your machine (outside)

```bash
chmod +x secure-bridge/sender/*.sh
# the background two-way loop (preferred — this is the "autosync" step):
bash secure-bridge/sender/autosync.sh
# or send a job once:
./secure-bridge/sender/push_job.sh myjob.py   # whole local file only
```

Push only whole local files. If you must stage a notebook for a one-off read
outbound (never in a job), use `git add` explicitly AFTER running the PHI scan
on it — the listener never does this automatically. Also copy
`sender/.env.example` → `.env` and fill in your fine-grained, repo-limited
read/write PAT; never commit the real one.

---

## Operation

Every step prints a short log to `bridge-state/bridge.log` on the server
(`--log-file` to change).

- **Send a job:** `push_job.sh jobs/roadsafety/clean_census.py`
- **Process once:** `listener.sh --once`
- **Watch loop:** run `listener.sh` (no flag) — default 20s interval, watches
  `bridge-inbox/jobs/` and `origin`.
- **Force a full outbound push:** `listener.sh --push-outbox`

---

## Replacing the inbox job model with direct repo PRs

The inbox is a thin single-path convenience. Because the listener executes
whatever arrives in `bridge-inbox/jobs/`, treat that folder like an
execution sandbox: reviewers must approve anything that lands there. A stricter
alternative is keeping `bridge-inbox/jobs` read-only to humans and only
merging PRs to a review branch (see `wake_on_git.py` for a poll-on-git
variant).

---

## Security & compliance notes

- **Raw PHI must never be logged** to stdout/stderr by jobs (it would flow to
  the outbox logs). Use aggregate values (counts, means, tables without
  identifiers) and write detailed content only to `bridge-outbox/`.
- The `phi_scan.py` gate is a best-effort pattern check for common IDs. It is
  **not** a certified DLP/IRM replacement — run an organization-approved
  scan/de-identification if your compliance requires it before enabling
  outbound pushes.
- Anyone with push rights to this repo could push code that the listener will
  execute on the PHI server. **Protect push access.** For team-wide exposure,
  strongly prefer a dedicated, access-restricted repo with branch protection
  and your org's identity-scoped secrets.

### Default secrets to rotate
| File | Default | Action required |
|------|---------|-----------------|
| `sender/.env.example` | `GIT_PUSH_TOKEN` placeholder | Fill with your fine-grained, read/write, repo-limited PAT; never commit the real one |

---

## Troubleshooting

- **`git pull` says already up to date but job isn't picked up** — the
  listener watches `bridge-inbox/jobs/`; confirm the file landed there in the
  server clone: `ls -la secure-bridge/bridge-inbox/jobs/`.
- **Outgoing files blocked** — run `phi_scan.py` on the file manually to see
  why: `python3 secure-bridge/receiver/phi_scan.py bridge-outbox/chart.png`.
- **Listener stopped** — check `logs` in `bridge-state/`; on JupyterHub, a
  running terminal tab is only alive while the server is up.
