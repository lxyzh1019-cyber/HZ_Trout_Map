#!/usr/bin/env python3
"""hz-loader — the only rules code kept in each app repository. Keep this file stable.

Every hook in .claude/settings.json calls:  hz-loader.py <hook-script>
- At session start it fetches the current central rules, hooks, worker instructions and skills from
  hz-claude-config (public raw files), caches them per version, then runs the requested hook script.
- Other hooks run the cached copy of the version the session started with.
- Offline: it reuses the last cached version and says so. Nothing cached: it tells the session to stop.
"""
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

SOURCE = os.environ.get("HZ_CENTRAL_URL",
                        "https://raw.githubusercontent.com/lxyzh1019-cyber/hz-claude-config/main/central/")
CACHE = os.environ.get("HZ_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "hz-rules")
KEEP_VERSIONS = 3


class Incomplete(Exception):
    """A file listed in MANIFEST.txt is missing on GitHub: hz-claude-config is incomplete, not unreachable."""


def fetch(rel):
    try:
        with urllib.request.urlopen(SOURCE + rel, timeout=10) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404 and rel != "MANIFEST.txt":
            raise Incomplete(f"hz-claude-config is incomplete on GitHub: {rel} is listed but missing") from e
        raise


def safe(rel):
    return rel and not rel.startswith(("/", "\\")) and ".." not in rel.replace("\\", "/").split("/")


def refresh():
    """Fetch MANIFEST and, if this version isn't cached yet, every file it lists. Returns (version, note)."""
    lines = fetch("MANIFEST.txt").decode("utf-8").splitlines()
    if not lines or not lines[0].lower().startswith("version:"):
        raise ValueError("MANIFEST.txt has no 'version:' first line")
    version = lines[0].split(":", 1)[1].strip()
    files = [l.strip() for l in lines[1:] if l.strip() and not l.startswith("#")]
    if not all(safe(f) for f in files):
        raise ValueError("MANIFEST.txt lists an unsafe path")
    target = os.path.join(CACHE, version)
    if not os.path.exists(os.path.join(target, ".complete")):
        tmp = target + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for rel, body in zip(files, pool.map(fetch, files)):
                path = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(body)
        with open(os.path.join(tmp, "MANIFEST.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        open(os.path.join(tmp, ".complete"), "w").close()
        shutil.rmtree(target, ignore_errors=True)
        os.replace(tmp, target)
    with open(os.path.join(CACHE, "current"), "w", encoding="utf-8") as f:
        f.write(version)
    prune()
    return version, ""


def prune():
    try:
        versions = sorted((d for d in os.listdir(CACHE) if os.path.isdir(os.path.join(CACHE, d)) and not d.endswith(".tmp")),
                          key=lambda d: os.path.getmtime(os.path.join(CACHE, d)), reverse=True)
        for d in versions[KEEP_VERSIONS:]:
            shutil.rmtree(os.path.join(CACHE, d), ignore_errors=True)
    except OSError:
        pass


def cached_version():
    try:
        v = open(os.path.join(CACHE, "current"), encoding="utf-8").read().strip()
        return v if os.path.exists(os.path.join(CACHE, v, ".complete")) else ""
    except OSError:
        return ""


def main():
    script = sys.argv[1] if len(sys.argv) > 1 else ""
    stdin = sys.stdin.buffer.read()
    os.makedirs(CACHE, exist_ok=True)
    note = ""
    if script == "session-start.py":
        try:
            version, note = refresh()
        except Exception as e:  # network, HTTP, or manifest problem
            version = cached_version()
            if not version:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                    "[session-start] Central rules NOT loaded: the loader could not fetch hz-claude-config "
                    f"({type(e).__name__}: {e}) and nothing is cached. Stop before any work and tell the user: "
                    "\"Central rules not loaded in this session.\""}}))
                return 0
            note = (f"hz-claude-config is incomplete on GitHub ({e}); using cached v{version} — tell the user in the "
                    "'I need from you' line that the rules repository needs repair" if isinstance(e, Incomplete)
                    else f"offline: using cached v{version} ({type(e).__name__})")
    else:
        version = cached_version()
        if not version:
            return 0  # session start already reported the problem
    path = os.path.join(CACHE, version, "hooks", script)
    if not safe(script) or not os.path.isfile(path):
        return 0
    # v3.2.7: the loader keeps compiled checks (no -B): the checks' compiled form stays in the rules cache, so a hook
    # call no longer compiles the large shared module again (a Read or Grep call took 1.2 s in the real sessions).
    env = dict(os.environ, HZ_LOADER_NOTE=note)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    r = subprocess.run([sys.executable, path], input=stdin, capture_output=True, env=env)
    sys.stdout.buffer.write(r.stdout)
    sys.stderr.buffer.write(r.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
