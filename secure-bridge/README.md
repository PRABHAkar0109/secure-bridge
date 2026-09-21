# Secure Bridge · Git-based "code in / results out" for protected workspaces

A lightweight, headless pipeline: you author **plain Python scripts** outside a
locked-down, PHI-protected environment (with any AI assistant or harness),
push them to a shared repo, and a listener on the secure server pulls +
executes them against the live data.

**What crosses back is intentionally minimal — schema and errors, not values:**
- **Outward (internal → you):** a **data skeleton** (`data_schema.md` — file
  path, row counts, column/field names, dtypes) and **error logs**
  (`<job>.error.txt` — tracebacks), both PHI-scanned.
- **Stays internal:** the actual analysis values/results/charts. You see them
  on the server; raw data and results never leak outward.

> **The two rules that keep this compliant:**
> - **In-bound** — only plain `.py` code crosses in. Never notebooks: notebooks
>   silently embed rendered PHI (dataframes, tracebacks, plots) in hidden
>   metadata.
> - **Out-bound** — only `data_schema.md` + `*.error.txt` under
>   `bridge-outbox/` cross back out, and only after passing
>   `receiver/phi_scan.py`, which blocks raw identifiers
>   (MRN/SSN/DOB/phone/email/name/address/secret patterns). Analysis values
>   never leave the server.

---

## Workflow (schema-first)

1. **Phase 0 — see the data first.** Send a probe job that reads your CSV/JSON
   on the server and writes **only its skeleton** to `OUTBOX/data_schema.md`
   (columns/field names, row counts, dtypes, source path). You receive it
   automatically.
2. **Phase 1 — push the real analysis.** Based on the schema, push your
   analysis code. It computes inside the secure workspace. If it raises an
   error, the full traceback returns to you in `<job>.error.txt` to fix.
3. **Results stay inside** — view charts/tables on the server, or have the
   analysis itself write only aggregates to the outbox if you opt in; by
   default the listener only returns schema + errors.

## Layout

```
secure-bridge/
├── README.md               <- this file (setup + operation)
├── template/
│   └── job_template.py     <- your "blank job" to fill in
├── sender/                 <- EXTERNAL workspace (your machine / any harness)
│   ├── push_job.sh         <- send one job
│   ├── autosync.sh         <- background two-way loop (pull results, push jobs)
│   └── .env.example        <- remote/branch/credentials template (never commit)
└── receiver/               <- INTERNAL workspace (the secure server)
    ├── listener.sh         <- pull + run + push loop (the engine)
    ├── runner.py           <- executes a job, captures stdout/stderr
    └── phi_scan.py         <- PHI/secret gate for anything leaving the server
```

The listener creates its working folders **inside its own clone only**:

```
<your secure workspace clone>/
└── secure-bridge/
    ├── bridge-inbox/jobs/  <- where job .py files land (pushed in)
    ├── bridge-outbox/      <- safe results are written here (pushed back)
    └── bridge-state/       <- logs + markers (local only, never pushed)
```

No other folder in the shared workspace is ever touched.

---

## How it works

```
  YOUR WORKSPACE (external)          git          SECURE WORKSPACE (internal)
 ┌──────────────────────────┐     ┌─────────┐     ┌─────────────────────────┐
 │ author job_template.py   │ ──► │         │ ──► │ listener pulls job      │
 │ push_job.sh / autosync   │     │ shared  │     │ runner executes it      │
 │                          │ ◄── │  repo   │ ◄── │ job writes bridge-outbox│
 │ review reports/charts    │     │         │     │ phi_scan gates the push │
 └──────────────────────────┘     └─────────┘     └─────────────────────────┘
```

1. **You (external)** fill `template/job_template.py` and save it to
   `secure-bridge/bridge-inbox/jobs/<jobname>.py` in your clone.
2. `sender/push_job.sh` stages **only** that file and pushes it (or
   `autosync.sh` does this automatically).
3. **Inside**, `receiver/listener.sh` pulls and runs each new/changed job with
   `runner.py` in the live environment; the job writes results **only** into
   `bridge-outbox/`.
4. Everything in `bridge-outbox/` is PHI-scanned by `phi_scan.py`; only passing
   files are committed and pushed back.
5. **You (external)** `git pull` (or autosync does) and review the transcript,
   tables/charts, and crash logs. PHI stays inside.

`bridge-outbox/` receives three kinds of file per job:
- `<jobname>.transcript.txt` — exact stdout of the run (plus bridge metadata)
- `<jobname>.crash.txt` on failure — the traceback, so you can fix it
- your report/chart artifacts (`summary.md`, `chart.png`, …) — write these from
  the job into `bridge-outbox/`

**Fix loop:** a crash log comes back → edit the job → the listener detects the
content change (checksum marker) and **auto re-runs it** on the next pass. No
manual steps on the server screen.

---

## Setup

### INTERNAL workspace — the secure server (one-time)

```bash
cd <your clone in the secure workspace>
chmod +x secure-bridge/receiver/*.sh secure-bridge/receiver/*.py

# run the listener in the background (survives terminal close):
./secure-bridge/receiver/listener.sh --daemon
# or run one pass to verify the wiring:
./secure-bridge/receiver/listener.sh --once
```

`--daemon` re-launches itself with `nohup`. On server/session restart the
daemon is gone — re-run it, or schedule `listener.sh --once` on a cron/login
hook to re-keep it alive. The default loop polls every 20s.

### EXTERNAL workspace — your machine (one-time)

```bash
cp secure-bridge/sender/.env.example secure-bridge/sender/.env
#   edit .env: GIT_REMOTE / GIT_BRANCH (fill GIT_PUSH_TOKEN if HTTPS-auth)
chmod +x secure-bridge/sender/*.sh

# send one job:
./secure-bridge/sender/push_job.sh myjob.py

# OR run the two-way loop in a dedicated terminal (watches + pulls):
bash secure-bridge/sender/autosync.sh
```

Use a **fine-grained PAT scoped read/write to this single repo**. Because the
listener executes whatever lands in `bridge-inbox/jobs/`, protecting push
access is how you keep the server safe — anyone who can push can run code on it.

---

## Guards you should not "fix" away

- **`phi_scan.py` fail-closed** — any block pattern refuses the whole outbox
  push; flagged files are moved to `bridge-state/quarantine/` and an audit
  line (counts/classes, never raw values) is appended to
  `bridge-state/phi-audit.jsonl`.
- **`.gitignore` deny-by-default** for raw data (`*.csv/xlsx/json/parquet`,
  notebooks, pickles) everywhere **except** `bridge-outbox/`, which is
  un-ignored because it is scanned before the listener may stage it.
- **Only `bridge-outbox/` crosses back.** Job stdout/stderr stays in
  `bridge-state/` logs on the server; transcripts ride the same PHI gate as
  everything else.
- **Self-test gate**: `listener.sh` refuses to start if
  `phi_scan.py --self-test` fails, so a broken scanner can't silently pass
  data.

These are **best-effort technical controls, not certified DLP/IRM**. Real
HIPAA/SOC2 attestation still requires vendor DLP, de-identification,
encryption, IAM, and signed BAAs — outside the scope of this pipeline.

---

## Running TWO projects at once (or more)

The pipeline is isolated by **branch + clone**. You can run two (or several)
independent projects simultaneously without them ever mixing.

**The rule:** each project on your machine gets its own folder (clone) **and**
its own branch in the shared repo; the internal side keeps a matching
clone + branch. Both scripts automatically use the branch they are checked
out on, so there is nothing to configure per project.

### EXTERNAL — your machine (two projects)

```bash
# Project A — clone once from the shared repo
git clone <shared-repo-url> my_project_A
cd my_project_A
git checkout -b project_a
cp secure-bridge/sender/.env.example secure-bridge/sender/.env
# start A's background loop (leave this terminal open)
bash secure-bridge/sender/autosync.sh

# Project B — clone a SECOND time into a different folder, different branch
git clone <shared-repo-url> my_project_B
cd my_project_B
git checkout -b project_b
cp secure-bridge/sender/.env.example secure-bridge/sender/.env
# start B's loop in its own terminal
bash secure-bridge/sender/autosync.sh
```

### INTERNAL — the secure workspace (matching clones/branches)

On the secure server, create two clones of the shared repo, check each out on
the matching branch, and start one listener per project:

```bash
# inside the shared work area:
git clone <shared-repo-url> project_A_clone && cd project_A_clone && git checkout -b project_a
./secure-bridge/receiver/listener.sh --daemon     # keep A alive

git clone <shared-repo-url> project_B_clone && cd project_B_clone && git checkout -b project_b
./secure-bridge/receiver/listener.sh --daemon     # keep B alive
```

Each pair (external clone/branch + internal clone/branch) now forms an
independent tunnel:
- A job pushed from `my_project_A` on branch `project_a` is picked up **only**
  by A's internal listener and its results return to A.
- Nothing crosses between A and B — different folders, different branches.

> Not sure if it's worth running them in parallel? Simpler alternative: run
> them one after another on the **same** clone/branch — same commands, one
> pipeline at a time.

---

## Operation

- **Send a job:** `push_job.sh jobs/roadsafety/clean_census.py`
- **Process once:** `listener.sh --once`
- **Watch loop (internal):** `listener.sh` (default 20s)
- **Two-way loop (external):** `autosync.sh`
- **Force a full outbox push:** `listener.sh --push-outbox`
- **Manual PHI scan:** `python3 secure-bridge/receiver/phi_scan.py <path>`
- **Self-test the gate:** `python3 secure-bridge/receiver/phi_scan.py --self-test`

---

## Troubleshooting

- **Job landed but never ran** — confirm the file is in the server clone:
  `ls -la secure-bridge/bridge-inbox/jobs/`
- **Outbox file blocked** — scan it manually to see why:
  `python3 secure-bridge/receiver/phi_scan.py bridge-outbox/<file>`
- **Listener stopped after a restart** — re-run `--daemon`, or schedule
  `--once` on a login hook/cron.
- **Push conflict on your machine** — `autosync.sh` rebases and retries
  automatically; if it gave up, run `push_job.sh <jobname>.py` once.
- **Check server logs** — `secure-bridge/bridge-state/bridge.log`.
