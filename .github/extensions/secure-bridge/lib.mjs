// Shared helpers for the Secure Bridge extension.
// All bridge operations run in the WORKTREE/repo the user has open
// (session.workspacePath). Everything is git-bridge-relative; this module
// never touches the secure server directly — the git bridge is the transport.
import { execFile } from "node:child_process";

const REPO = process.cwd(); // workspace root (git root of this repo)

export function repoRoot() {
  return REPO;
}

export function run(cmd, args, { cwd = REPO, allowFail = false } = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { cwd, timeout: 120000 }, (err, stdout, stderr) => {
      if (err && !allowFail) {
        resolve({ ok: false, code: err.code ?? "error", stdout, stderr: stderr || err.message });
      } else {
        resolve({ ok: true, code: err?.code ?? 0, stdout, stderr });
      }
    });
  });
}

// --- paths inside the repo ---
export const BRIDGE = () => `${REPO}/secure-bridge`;
export const INBOX = () => `${BRIDGE()}/bridge-inbox/jobs`;
export const OUTBOX = () => `${BRIDGE()}/bridge-outbox`;
export const STATE = () => `${BRIDGE()}/bridge-state`;
export const AUTOSYNC = () => `${BRIDGE()}/sender/autosync.sh`;
export const PUSH_JOB = () => `${BRIDGE()}/sender/push_job.sh`;
export const LISTENER = () => `${BRIDGE()}/receiver/listener.sh`;
export const PHI_SCAN = () => `${BRIDGE()}/receiver/phi_scan.py`;

export async function listInbox() {
  const r = await run("ls", [INBOX()], { allowFail: true });
  if (!r.ok) return [];
  return r.stdout.split("\n").filter((s) => s.trim());
}

export async function listOutbox() {
  const r = await run("ls", [OUTBOX()], { allowFail: true });
  if (!r.ok) return [];
  return r.stdout.split("\n").filter((s) => s.trim());
}

export async function readOutboxFile(name) {
  if (!name || name.includes("/") || name.includes("..")) {
    return { ok: false, error: "invalid file name" };
  }
  const r = await run("cat", [`${OUTBOX()}/${name}`], { allowFail: true });
  return r; // { ok, stdout (contents), stderr }
}

export async function gitStatus() {
  const r = await run("git", ["status", "--porcelain"], { cwd: REPO });
  return r;
}

export async function gitLog(n = 12) {
  const r = await run(
    "git",
    ["log", "--oneline", `-${n}`, "--", "secure-bridge/"],
    { cwd: REPO, allowFail: true }
  );
  return r;
}

export async function phiScan(target) {
  // target is a path inside the repo (relative or absolute)
  const r = await run("python3", [PHI_SCAN(), target], { cwd: REPO, allowFail: true });
  return { ok: r.ok, stdout: r.stdout, stderr: r.stderr };
}
