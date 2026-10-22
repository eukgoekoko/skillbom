#!/usr/bin/env python3
"""Draw the accuracy sample and write blind evidence packets for labeling.

One random skill from each of N random repositories (repo-weighted, like the study's
headline numbers). Packets show the raw license evidence around each skill but not the
scanner's verdict, so labels can be made blind.

Writes <out>/sample.jsonl and <out>/packets-NN.md (25 per file). Usage:
  sample.py                                          # training set: 200 skills, .corpus/accuracy
  sample.py --name holdout --n 100 --seed 7 --exclude .corpus/accuracy/sample.jsonl
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".corpus"
PER_FILE = 25
LICENSE_NAME = re.compile(r"^((un)?licen[cs]e|copying|notice|skill-license\.)", re.I)


def head(path: Path, lines: int = 8, width: int = 110) -> list[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        return [f"<unreadable: {e}>"]
    out = [l.strip()[:width] for l in text.splitlines() if l.strip()]
    return out[:lines] + ([f"... ({len(out) - lines} more lines)"] if len(out) > lines else [])


def frontmatter_license(skill_md: Path) -> list[str]:
    try:
        text = skill_md.read_text(errors="replace")
    except OSError:
        return ["<no SKILL.md>"]
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    fm = m.group(1) if m else ""
    hits = [l.strip()[:150] for l in fm.splitlines() if re.search(r"licen[cs]e", l, re.I)]
    body = text[m.end():] if m else text
    body_hits = [l.strip()[:150] for l in body.splitlines() if re.search(r"licen[cs]e", l, re.I)][:3]
    return ([f"frontmatter: {h}" for h in hits] or ["frontmatter: (no license key)"]) + \
           [f"body: {h}" for h in body_hits]


def manifest_license(d: Path) -> list[str]:
    out = []
    for rel in (".claude-plugin/plugin.json", "package.json"):
        p = d / rel
        if p.is_file():
            try:
                lic = json.loads(p.read_text()).get("license")
            except (OSError, ValueError, AttributeError):
                lic = "<unparsable>"
            out.append(f"{rel}: license = {json.dumps(lic)}")
    return out


def packet(sid: str, repo: str, rel: str) -> str:
    root = CORPUS / "repos" / repo
    skill = root / rel
    lines = [f"## {sid}  {repo}  /{rel}", ""]
    lines += [f"    {l}" for l in frontmatter_license(skill / "SKILL.md")]
    own = sorted(p for p in skill.iterdir() if p.is_file() and LICENSE_NAME.match(p.name))
    for p in own:
        lines.append(f"    [skill dir] {p.name}:")
        lines += [f"        {l}" for l in head(p)]
    lines += [f"    [skill dir] {m}" for m in manifest_license(skill)]
    d = skill
    while d != root:
        d = d.parent
        where = "/" + str(d.relative_to(root)) if d != root else "(repo root)"
        for p in sorted(p for p in d.iterdir() if p.is_file() and LICENSE_NAME.match(p.name)):
            lines.append(f"    [{where}] {p.name}:")
            lines += [f"        {l}" for l in head(p)]
        lines += [f"    [{where}] {m}" for m in manifest_license(d)]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="", help="subdirectory of .corpus/accuracy (default: none)")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--exclude", type=Path, action="append", default=[], help="sample.jsonl whose repos to skip")
    args = ap.parse_args()
    out = CORPUS / "accuracy" / args.name
    excluded = {json.loads(l)["repo"] for f in args.exclude for l in f.read_text().splitlines()}
    rng = random.Random(args.seed)
    repos = []
    for f in sorted((CORPUS / "boms").glob("*.json")):
        if f.stem in excluded:
            continue
        bom = json.loads(f.read_text())
        skills = [c for c in bom["components"] if c["kind"] == "skill"]
        if skills:
            repos.append((f.stem, skills))
    picked = rng.sample(repos, min(args.n, len(repos)))
    out.mkdir(parents=True, exist_ok=True)
    sample, packets = [], []
    for i, (repo, skills) in enumerate(picked, 1):
        c = rng.choice(skills)
        rel = c["installations"][0]["path"].removeprefix("~/").removeprefix("~")
        sample.append({"id": f"{'H' if args.name else 'S'}{i:03d}", "repo": repo, "path": rel, "bomRef": c["bomRef"]})
        packets.append(packet(sample[-1]["id"], repo, rel))
    with (out / "sample.jsonl").open("w") as f:
        for s in sample:
            f.write(json.dumps(s) + "\n")
    for k in range(0, len(packets), PER_FILE):
        (out / f"packets-{k // PER_FILE + 1:02d}.md").write_text("\n".join(packets[k:k + PER_FILE]))
    print(f"{len(sample)} skills from {len(repos)} repos -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
