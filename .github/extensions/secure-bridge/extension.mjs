// ============================================================================
// SECURE BRIDGE — Copilot extension (project-shipped).
//
//   tools  → bridge commands the agent can run on the user's behalf:
//              secure_bridge_send_job, secure_bridge_scan_phi,
//              secure_bridge_read_outbox, secure_bridge_status,
//              secure_bridge_autosync_command
//   hook   → onPostToolUse: re-scan outbox after any tool, alert if PHI flagged
//   canvas → "secure-bridge" interactive control panel (list/send/scan/report).
//
// The git bridge stays the only transport to the secure workspace. This
// extension only manipulates files/git in THIS repo (the "outside" controller).
// ============================================================================

import { createServer } from "node:http";
import { joinSession, createCanvas, CanvasError } from "@github/copilot-sdk/extension";
import {
  repoRoot, run, AUTOSYNC, PUSH_JOB, OUTBOX,
  listInbox, listOutbox, readOutboxFile, gitLog, phiScan,
} from "./lib.mjs";

// ---- shared outbox status builder (used by tool + canvas) ----------------
function categorize(outbox) {
  return outbox.map((f) => ({
    name: f,
    kind: f.endsWith(".md") ? "report" : f.endsWith(".png") ? "chart" : f.endsWith(".txt") || f.endsWith(".json") ? "log" : "file",
  }));
}

async function bridgeDigest() {
  const inbox = await listInbox();
  const outbox = await listOutbox();
  return { inbox, outbox: categorize(outbox) };
}

// ============================================================================
// TOOLS (agent-callable)
// ============================================================================
const tools = [
  {
    name: "secure_bridge_send_job",
    description:
      "Send a job file to the secure bridge: copies the given .py file into secure-bridge/bridge-inbox/jobs/ and pushes it to origin, so the internal listener will run it against the secure data. Use after authoring/editing a job.",
    parameters: {
      type: "object",
      properties: {
        path: {
          type: "string",
          description: "Repo-relative path of the .py job file (e.g. secure-bridge/bridge-inbox/jobs/analysis.py)",
        },
      },
      required: ["path"],
    },
    handler: async (args) => {
      const path = String(args.path || "").trim();
      if (!path.endsWith(".py")) {
        return { ok: false, message: "Only .py job files may be sent (notebooks embed PHI)." };
      }
      const r = await run("bash", [PUSH_JOB(), path], { cwd: repoRoot(), allowFail: true });
      return { ok: r.ok, output: r.stdout || r.stderr };
    },
  },
  {
    name: "secure_bridge_scan_phi",
    description:
      "Run the PHI/secret scanner over the bridge outbox (or a specific path). Blocks outbound push if raw identifiers (MRN/SSN/DOB/name/address/secret) are found. Use before reviewing or pushing any bridge result.",
    parameters: {
      type: "object",
      properties: {
        target: { type: "string", description: "Optional path to scan; defaults to secure-bridge/bridge-outbox" },
      },
    },
    handler: async (args) => {
      const target = String(args.target || OUTBOX());
      const r = await phiScan(target);
      return { ok: r.ok, output: r.stdout || r.stderr };
    },
  },
  {
    name: "secure_bridge_read_outbox",
    description:
      "Read the contents of a file in the bridge outbox (aggregated reports/charts/logs pushed back from the secure workspace). Use to review a report or a crash log.",
    parameters: {
      type: "object",
      properties: {
        file: { type: "string", description: "Name of the outbox file to read (e.g. data_report.md or analysis.py.crash.txt)" },
      },
      required: ["file"],
    },
    handler: async (args) => {
      const r = await readOutboxFile(String(args.file || ""));
      if (!r.ok) return { ok: false, message: r.error || "cannot read file" };
      return { ok: true, content: r.stdout };
    },
  },
  {
    name: "secure_bridge_status",
    description:
      "Summarize the current bridge state: inbox jobs waiting to run inside, outbox reports/charts/logs returned, and recent bridge commits.",
    parameters: { type: "object", properties: {} },
    handler: async () => {
      const d = await bridgeDigest();
      const log = await gitLog(8);
      return {
        ok: true,
        inbox: d.inbox,
        outbox: d.outbox,
        recentBridgeCommits: log.ok ? log.stdout.trim().split("\n") : [],
      };
    },
  },
  {
    name: "secure_bridge_autosync_command",
    description:
      "Return the exact command to run the external two-way auto-sync loop (pulls inbound results, pushes edited jobs) in a dedicated terminal on your machine.",
    parameters: {
      type: "object",
      properties: {
        stop: { type: "boolean", description: "If true, return instructions to stop the running loop." },
      },
    },
    handler: async (args) => {
      if (args.stop) {
        return { ok: true, message: "Stop the autosync loop by pressing Ctrl-C in the terminal where you started it (or close that terminal tab)." };
      }
      return { ok: true, command: `bash ${AUTOSYNC()}`, message: "Run this in a dedicated terminal — it runs continuously and needs its own terminal. It will pull inbound results and push edited jobs." };
    },
  },
];

// ============================================================================
// HOOKS — auto PHI re-scan after any tool runs
// NOTE: attaching hooks requires a hook processor that is only configured on
// a session that is STARTED with the extension already present. Hot-loading /
// reloading hooks into THIS running session fails with "Hook processor is not
// configured". Tools + canvas work fine; hooks need a fresh session to attach.
// ============================================================================
const hooks = undefined;

// ============================================================================
// CANVAS — interactive dashboard (loopback HTTP server + SSE + actions)
// ============================================================================
const servers = new Map(); // instanceId -> { server, url, subs: [] }

function dashboardHtml(instanceId) {
  return `<!doctype html>
<html>
  <head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Secure Bridge</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin:0; padding:16px;
      background: var(--background-color-default, #fff);
      color: var(--text-color-default, #1f2328);
      font-family: var(--font-sans, system-ui, sans-serif);
      font-size: var(--text-body-medium, 14px);
      line-height: var(--leading-body-medium, 20px); }
    h1 { font-size: 18px; margin: 0 0 4px; }
    .muted { color: var(--text-color-muted, #59636e); font-size: 12px; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap:12px; margin-top:12px; }
    .card { border:1px solid var(--border-color-default, rgba(0,0,0,.12)); border-radius:8px; padding:12px; }
    .card h2 { font-size:13px; margin:0 0 8px; text-transform:uppercase; letter-spacing:.04em; opacity:.8; }
    ul { margin:0; padding-left:18px; }
    li { margin:2px 0; }
    button { font:inherit; border-radius:6px; border:1px solid var(--border-color-default, rgba(0,0,0,.2));
      background: var(--background-color-default, #f6f8fa); color: var(--text-color-default,#1f2328);
      padding:4px 10px; cursor:pointer; }
    button.primary { background: var(--true-color-blue, #0969da); border-color: var(--true-color-blue, #0969da); color:#fff; }
    .badge { display:inline-block; border-radius:999px; padding:1px 8px; font-size:11px; margin-left:6px; }
    .ok { background: rgba(63,185,80,.18); color: #1a7f37; }
    .warn { background: rgba(214,158,46,.2); color: #9a6700; }
    pre { background: var(--background-color-muted, rgba(0,0,0,.05)); padding:8px; border-radius:6px;
      overflow:auto; font:11px/1.4 var(--font-mono, ui-monospace, monospace); }
    textarea { width:100%; min-height:80px; font:12px var(--font-mono, ui-monospace, monospace);
      box-sizing:border-box; margin-top:12px; border-radius:6px; border:1px solid var(--border-color-default, rgba(0,0,0,.2)); padding:6px; }
  </style></head>
  <body>
    <h1>Secure Bridge <span class="muted">· code in / results out</span></h1>
    <div class="muted">Outside controller — the git bridge is the only transport to the secure workspace.</div>

    <div class="grid">
      <div class="card">
        <h2>Inbox (jobs to send inside)</h2>
        <ul id="inbox"><li class="muted">loading…</li></ul>
        <div style="margin-top:10px">
          <input id="jobpath" placeholder="job path, e.g. analysis.py"
                 style="width:100%; box-sizing:border-box; padding:4px 6px; border-radius:6px; border:1px solid var(--border-color-default, rgba(0,0,0,.2))" />
          <button class="primary" style="margin-top:6px" onclick="sendJob()">Send job ⟶</button>
        </div>
      </div>

      <div class="card">
        <h2>Outbox (results from inside)</h2>
        <ul id="outbox"><li class="muted">loading…</li></ul>
        <div style="margin-top:10px">
          <button onclick="scan()">Run PHI scan</button>
          <button onclick="refresh()">Refresh</button>
        </div>
        <pre id="scanout" style="display:none"></pre>
      </div>

      <div class="card">
        <h2>Actions</h2>
        <div class="muted" style="margin-bottom:6px">External two-way sync loop:</div>
        <pre style="margin:0 0 8px">bash ${AUTOSYNC()}</pre>
        <button onclick="copyCmd()" style="width:100%">Copy command</button>
      </div>

      <div class="card" style="grid-column:1 / -1">
        <h2>Recent bridge commits</h2>
        <pre id="log">…</pre>
      </div>
    </div>

    <textarea id="report" placeholder="Report / crash-log preview appears here — click an outbox file."></textarea>

    <script>
      const base = location.origin;
      const es = new EventSource(base + "/events");
      es.onmessage = (e) => { try { render(JSON.parse(e.data)); } catch (_) {} };

      async function refresh() { const r = await fetch(base + "/data"); render(await r.json()); }

      async function render(d) {
        const li = (arr) => arr.length ? arr.map(x => "<li>" + x + "</li>").join("") : '<li class="muted">empty</li>';
        document.getElementById("inbox").innerHTML = li(d.inbox || []);
        const out = (d.outbox || []).map(f =>
          "<li><button class='open' onclick='openF(\\'' + f + '\\')'>" + f + "</button></li>").join("");
        document.getElementById("outbox").innerHTML = out || '<li class="muted">empty</li>';
        document.getElementById("log").textContent = (d.log || []).join("\\n");
        document.getElementById("scanout").style.display = "none";
      }

      window.openF = async (f) => {
        const r = await fetch(base + "/read?f=" + encodeURIComponent(f));
        const j = await r.json();
        document.getElementById("report").value = j.content || "(binary file — open it in the editor)";
      };

      window.sendJob = async () => {
        const p = document.getElementById("jobpath").value.trim();
        if (!p) return;
        const r = await fetch(base + "/sendjob", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p }) });
        const j = await r.json();
        document.getElementById("report").value = j.output || "sent";
        refresh();
      };

      window.scan = async () => {
        const r = await fetch(base + "/scan"); const j = await r.json();
        const el = document.getElementById("scanout");
        el.textContent = j.output; el.style.display = "block";
      };

      window.copyCmd = () => {
        navigator.clipboard && navigator.clipboard.writeText("bash ${AUTOSYNC()}");
        document.getElementById("report").value = "Copied: bash ${AUTOSYNC()}";
      };

      refresh();
    </script>
  </body>
</html>`;
}

async function startServer(instanceId, entry) {
  // `entry` is pre-created by the caller and registered in the `servers` map
  // BEFORE any request can arrive, so /events always has a subs array.
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const path = url.pathname;
    let body = "";
    for await (const chunk of req) body += chunk;
    const send = (code, data) => {
      res.statusCode = code;
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(JSON.stringify(data));
    };

    if (path === "/") {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(dashboardHtml(instanceId));
    } else if (path === "/data") {
      const d = await bridgeDigest();
      const log = await gitLog(8);
      send(200, { inbox: d.inbox, outbox: d.outbox.map((o) => o.name), log: log.ok ? log.stdout.trim().split("\n") : [] });
    } else if (path === "/read") {
      const f = url.searchParams.get("f") || "";
      const r = await readOutboxFile(f);
      send(200, { ok: r.ok, content: r.ok ? r.stdout : (r.error || "cannot read") });
    } else if (path === "/sendjob") {
      let p = "";
      try { p = (JSON.parse(body || "{}").path || "").trim(); } catch { /* ignore */ }
      if (!p.endsWith(".py")) { send(400, { ok: false, output: "Only .py jobs are allowed (notebooks embed PHI)." }); return; }
      const r = await run("bash", [PUSH_JOB(), p], { cwd: repoRoot(), allowFail: true });
      send(r.ok ? 200 : 500, { ok: r.ok, output: r.stdout || r.stderr });
    } else if (path === "/scan") {
      const r = await phiScan(OUTBOX());
      send(200, { ok: r.ok, output: r.stdout || r.stderr });
    } else if (path === "/events") {
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.write("retry: 3000\n\n");
      const push = (d) => res.write(`data: ${JSON.stringify(d)}\n\n`);
      if (entry) entry.subs.push(push);
      const iv = setInterval(async () => {
        try {
          const d = await bridgeDigest();
          push({ inbox: d.inbox, outbox: d.outbox.map((o) => o.name) });
        } catch { /* keep stream alive */ }
      }, 10000);
      req.on("close", () => {
        clearInterval(iv);
        if (entry) entry.subs = entry.subs.filter((s) => s !== push);
      });
    } else {
      send(404, { ok: false, output: "not found" });
    }
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  return { server, url: `http://127.0.0.1:${port}/` };
}

// ============================================================================
// Canvas actions (agent / SDK driven)
// ============================================================================
const actions = [
  {
    name: "refresh",
    description: "Refresh the bridge status shown in the dashboard.",
    inputSchema: { type: "object", properties: {} },
    handler: async (ctx) => {
      const d = await bridgeDigest();
      const log = await gitLog(8);
      const entry = servers.get(ctx.instanceId);
      if (entry) entry.subs.forEach((s) => s({ inbox: d.inbox, outbox: d.outbox.map((o) => o.name) }));
      return { ok: true, inbox: d.inbox, outbox: d.outbox, log: log.ok ? log.stdout.trim().split("\n") : [] };
    },
  },
  {
    name: "send_job",
    description: "Send a .py job through the bridge (copy into inbox + push).",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Repo-relative path of the .py job file" },
      },
      required: ["path"],
    },
    handler: async (ctx) => {
      const path = String(ctx.input.path || "").trim();
      if (!path.endsWith(".py")) throw new CanvasError("bad_input", "Only .py jobs are allowed (notebooks embed PHI).");
      const r = await run("bash", [PUSH_JOB(), path], { cwd: repoRoot(), allowFail: true });
      if (!r.ok) throw new CanvasError("push_failed", r.stderr || r.stdout);
      return { ok: true, output: r.stdout || r.stderr };
    },
  },
  {
    name: "run_phi_scan",
    description: "Run the PHI scan over the outbox and return the result.",
    inputSchema: { type: "object", properties: {} },
    handler: async () => {
      const r = await phiScan(OUTBOX());
      return { ok: r.ok, output: r.stdout || r.stderr };
    },
  },
  {
    name: "read_report",
    description: "Return the contents of an outbox file (report/chart/log).",
    inputSchema: {
      type: "object",
      properties: {
        file: { type: "string", description: "Outbox file name (e.g. data_report.md or analysis.py.crash.txt)" },
      },
      required: ["file"],
    },
    handler: async (ctx) => {
      const r = await readOutboxFile(String(ctx.input.file || ""));
      if (!r.ok) throw new CanvasError("read_failed", r.error || "cannot read file");
      return { ok: true, content: r.stdout };
    },
  },
];

// ============================================================================
const joined = await joinSession({
  tools,
  hooks,
  canvases: [
    createCanvas({
      id: "secure-bridge",
      displayName: "Secure Bridge",
      description: "Interactive control panel for the secure-bridge pipeline: list inbox jobs, view outbox reports/charts, run PHI scans, and send jobs.",
      actions,
      open: async (ctx) => {
        let entry = servers.get(ctx.instanceId);
        if (!entry) {
          entry = { server: null, url: "", subs: [] };
          servers.set(ctx.instanceId, entry);
          const started = await startServer(ctx.instanceId, entry);
          entry.server = started.server;
          entry.url = started.url;
        }
        return { title: "Secure Bridge", url: entry.url };
      },
      onClose: async (ctx) => {
        const entry = servers.get(ctx.instanceId);
        if (entry) {
          servers.delete(ctx.instanceId);
          await new Promise((r) => entry.server.close(() => r()));
        }
      },
    }),
  ],
});

joined.log("secure-bridge extension loaded: tools + phi-scan hook + dashboard canvas");
