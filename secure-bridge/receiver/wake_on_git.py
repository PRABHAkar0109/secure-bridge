#!/usr/bin/env python3
# ============================================================================
# WAKE-ON-GIT (secure server) — alternate trigger for the listener.
#
# Tails a "signal" branch or the inbox by polling the remote, and invokes
# listener.sh --once on change. Lets you use branch-protected reviews
# instead of a raw inbox if your org requires it.
#
# Usage: python3 wake_on_git.py            # watch origin/main
#        python3 wake_on_git.py -b review  # watch a review branch
# ============================================================================
import argparse
import os
import subprocess
import time

DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
LISTENER = os.path.join(SCRIPT_DIR, "listener.sh")


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args],
                          capture_output=True, text=True)


def last_remote_sha(remote, branch):
    r = git("ls-remote", remote, f"refs/heads/{branch}")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.split()[0]


def run_listener_once():
    subprocess.run([LISTENER, "--once"], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-b", "--branch", default=DEFAULT_BRANCH)
    ap.add_argument("-r", "--remote", default=DEFAULT_REMOTE)
    ap.add_argument("--poll", type=int, default=20)
    args = ap.parse_args()
    print(f"watching {args.remote}/{args.branch} every {args.poll}s")

    last = None
    while True:
        cur = last_remote_sha(args.remote, args.branch)
        if cur is not None and cur != last:
            print(f"change detected {last} -> {cur}; running listener --once")
            run_listener_once()
            last = cur
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
