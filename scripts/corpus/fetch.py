#!/usr/bin/env python3
"""Fetch the skill-relevant files of every repository in .corpus/sources.jsonl into .corpus/repos/.

Uses a shallow partial clone (blobs over 1 MB are never downloaded) and checks out only:
  - every file under a directory containing SKILL.md
  - plugin roots' top-level files and .claude-plugin/ (nested skills are covered above)
  - LICENSE*/COPYING*/skill-license.* files at any depth
So content hashes in the corpus cover a filtered tree; they are comparable within the
corpus (same filter everywhere) but not with hashes of full installs.

Needs git >= 2.27 (set GIT=/path/to/git). Existing repositories are kept, so the script
resumes. Writes .corpus/fetch.jsonl: {"repo", "ok", "commit", "files", "error", "seconds"}.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".corpus"
GIT = os.environ.get("GIT", "/usr/bin/git")
WORKERS = 12
TIMEOUT = 300
BLOB_LIMIT = "1m"
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
ALWAYS = re.compile(r"^((un)?licen[cs]e|copying|skill-license\.)", re.I)


def git(*args, cwd=None, input=None, timeout=TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run([GIT, *args], cwd=cwd, env=ENV, input=input, capture_output=True,
                          timeout=timeout, check=True)


def wanted(paths: list[str]) -> list[str]:
    skill_dirs = {str(PurePosixPath(p).parent) for p in paths if PurePosixPath(p).name == "SKILL.md"}
    plugin_roots = {str(PurePosixPath(p).parent.parent) for p in paths if p.endswith(".claude-plugin/plugin.json")}

    def under(p: str, dirs: set[str]) -> bool:
        parents = {str(a) for a in PurePosixPath(p).parents}
        return bool(parents & dirs)

    out = []
    for p in paths:
        pp = PurePosixPath(p)
        if (ALWAYS.match(pp.name) or under(p, skill_dirs) or str(pp.parent) in plugin_roots
                or "/.claude-plugin/" in f"/{p}"):
            out.append(p)
    return out


def fetch(src: dict) -> dict:
    dest = CORPUS / "repos" / src["repo"].replace("/", "__")
    result = {"repo": src["repo"], "ok": False, "commit": None, "files": None, "error": None, "seconds": 0.0}
    start = time.monotonic()
    try:
        if not (dest / ".git").is_dir():
            shutil.rmtree(dest, ignore_errors=True)
            git("clone", "--quiet", "--depth", "1", f"--filter=blob:limit={BLOB_LIMIT}", "--no-checkout",
                src["url"], str(dest))
            tree = git("ls-tree", "-r", "-z", "--full-tree", "HEAD", cwd=dest).stdout.split(b"\0")
            entries = [e.decode(errors="surrogateescape").split("\t", 1) for e in tree if e]
            missing = {l[1:] for l in git("rev-list", "--objects", "--missing=print", "HEAD", cwd=dest)
                       .stdout.decode().splitlines() if l.startswith("?")}
            files = [path for meta, path in entries
                     if meta.split()[1] == "blob" and meta.split()[2] not in missing]
            keep = wanted(files)
            if keep:
                git("--literal-pathspecs", "checkout", "--quiet", "HEAD", "--pathspec-from-file=-",
                    "--pathspec-file-nul", cwd=dest, input=b"\0".join(k.encode(errors="surrogateescape") for k in keep))
            result["files"] = len(keep)
        result["commit"] = git("rev-parse", "HEAD", cwd=dest).stdout.decode().strip()
        result["ok"] = True
    except subprocess.TimeoutExpired:
        result["error"] = f"timeout after {TIMEOUT}s"
    except subprocess.CalledProcessError as e:
        result["error"] = ((e.stderr or b"").decode(errors="replace").strip().splitlines() or ["git failed"])[-1][:300]
    if not result["ok"]:
        shutil.rmtree(dest, ignore_errors=True)
    result["seconds"] = round(time.monotonic() - start, 1)
    return result


def main() -> int:
    sources = [json.loads(line) for line in (CORPUS / "sources.jsonl").read_text().splitlines()]
    (CORPUS / "repos").mkdir(parents=True, exist_ok=True)
    done = ok = 0
    with ThreadPoolExecutor(WORKERS) as pool, (CORPUS / "fetch.jsonl").open("w") as log:
        for fut in as_completed([pool.submit(fetch, s) for s in sources]):
            r = fut.result()
            log.write(json.dumps(r) + "\n")
            log.flush()
            done += 1
            ok += r["ok"]
            if done % 50 == 0 or done == len(sources):
                print(f"{done}/{len(sources)} done, {ok} ok", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
