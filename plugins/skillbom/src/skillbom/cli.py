"""Command line: `skillbom scan`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillbom import __version__, discover
from skillbom.bom import build
from skillbom.report import render
from skillbom.rules import Policy


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillbom", description=__doc__)
    p.add_argument("--version", action="version", version=f"skillbom {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="scan this host and write a Skill BOM (JSON)")
    s.add_argument("--home", type=Path, default=Path.home(), help="home directory to scan (default: yours)")
    s.add_argument("--no-home", action="store_true", help="skip the home directory and managed locations")
    s.add_argument("--project", type=Path, action="append", default=[], metavar="DIR",
                   help="also scan DIR/.claude/skills and DIR/.codex/skills (repeatable)")
    s.add_argument("--root", type=Path, action="append", default=[], metavar="DIR",
                   help="also scan DIR recursively for skills and plugins (repeatable)")
    s.add_argument("--include-catalogs", action="store_true",
                   help="include plugins available in marketplace clones but not installed")
    s.add_argument("--policy", type=Path, help="YAML policy (allowedLicenses, deniedLicenses, severities)")
    s.add_argument("--organization", help="organization name for the report metadata")
    s.add_argument("-o", "--output", type=Path, help="write the BOM here instead of stdout")
    s.add_argument("--html", type=Path, metavar="FILE", help="also write an HTML audit report")
    s.add_argument("-q", "--quiet", action="store_true", help="no summary on stderr")
    r = sub.add_parser("report", help="render a Skill BOM (JSON) as an HTML audit report")
    r.add_argument("bom", type=Path, help="Skill BOM JSON file")
    r.add_argument("-o", "--output", type=Path, required=True, help="HTML file to write")
    r.add_argument("--title", help="report title (default: from the organization name)")
    return p


def _summary(bom: dict) -> str:
    s = bom["summary"]
    lines = [f"{s['components']} components, {s['installations']} installations",
             "licenses: " + ", ".join(f"{k} {v}" for k, v in s["byLicense"].items())]
    sev = {k: v for k, v in s["findingsBySeverity"].items() if v}
    lines.append("findings: " + (", ".join(f"{k} {v}" for k, v in sev.items()) if sev else "none"))
    for f in bom["findings"]:
        if f["severity"] != "info":
            lines.append(f"  [{f['severity']}] {f['rule']}: {f['message']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "report":
        args.output.write_text(render(json.loads(args.bom.read_text()), title=args.title))
        return 0
    home = args.home.expanduser().resolve()
    candidates: list[discover.Candidate] = []
    roots: list[Path] = []
    if not args.no_home:
        candidates += discover.claude_code(home, include_catalogs=args.include_catalogs)
        candidates += discover.codex(home)
        candidates += discover.managed()
        roots += [home / ".claude", home / ".codex"]
    for d in (p.expanduser().resolve() for p in args.project):
        candidates += discover.project(d)
        roots.append(d)
    for d in (p.expanduser().resolve() for p in args.root):
        candidates += discover.scan_tree(d, "claude-code", "local")
        roots.append(d)

    policy = Policy.load(args.policy) if args.policy else None
    bom = build(candidates, roots=roots, policy=policy, home=home, organization=args.organization)

    text = json.dumps(bom, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    if args.html:
        args.html.write_text(render(bom))
    if not args.quiet:
        print(_summary(bom), file=sys.stderr)
    return 0
