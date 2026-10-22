#!/usr/bin/env python3
"""Build the list of public skill/plugin repositories to study.

Sources:
  - external plugin sources in the official Claude Code marketplace (local clone)
  - GitHub repository search for skill/plugin topics (unauthenticated: 10 req/min)

Writes .corpus/sources.jsonl: one {"repo", "url", "origins", "stars"} per repository.
Set GITHUB_TOKEN to raise rate limits.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".corpus/sources.jsonl"
MARKETPLACE = Path.home() / ".claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json"
QUERIES = [
    "topic:claude-skills",
    "topic:agent-skills",
    "topic:claude-code-skills",
    "topic:claude-code-plugin",
    "topic:claude-code-plugins",
    "topic:claude-skill",
    "claude skills in:name,description",
    "SKILL.md in:readme",
]
PAGES = 2  # 100 results per page


def repo_key(url: str) -> str | None:
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}".lower()


def github(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}", headers={"Accept": "application/vnd.github+json"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    repos: dict[str, dict] = {}

    def add(key, origin, stars=None):
        r = repos.setdefault(key, {"repo": key, "url": f"https://github.com/{key}.git", "origins": [], "stars": None})
        if origin not in r["origins"]:
            r["origins"].append(origin)
        if stars is not None:
            r["stars"] = stars

    add("anthropics/skills", "seed")
    for entry in json.loads(MARKETPLACE.read_text())["plugins"]:
        src = entry.get("source")
        url = src.get("url") if isinstance(src, dict) else None
        if isinstance(src, dict) and src.get("repo"):
            url = f"https://github.com/{src['repo']}"
        if url and (key := repo_key(url)):
            add(key, "official-marketplace")
    print(f"marketplace: {len(repos)} repos", file=sys.stderr)

    for q in QUERIES:
        for page in range(1, PAGES + 1):
            params = urllib.parse.urlencode({"q": q, "sort": "stars", "per_page": 100, "page": page})
            try:
                items = github(f"/search/repositories?{params}")["items"]
            except Exception as e:  # rate limit or network: keep what we have
                print(f"search {q!r} page {page}: {e}", file=sys.stderr)
                time.sleep(61)
                continue
            for it in items:
                if not it.get("fork") and not it.get("archived"):
                    add(it["full_name"].lower(), f"search:{q}", it["stargazers_count"])
            print(f"search {q!r} page {page}: {len(items)} -> {len(repos)} repos", file=sys.stderr)
            time.sleep(7)  # stay under 10 searches/minute
            if len(items) < 100:
                break

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        for r in sorted(repos.values(), key=lambda r: r["repo"]):
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(repos)} repos to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
