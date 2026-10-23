#!/usr/bin/env python3
"""Build the public sample report from invented skills on three invented machines.

Writes docs/demo/skillbom.json and docs/demo/report.html. Every skill, company and
machine here is fictional, so the sample shows every license category and rule
without pointing at real projects.
"""
import json
import tempfile
from pathlib import Path

from skillbom import discover
from skillbom.bom import build
from skillbom.hashing import content_hash
from skillbom.merge import merge
from skillbom.report import render
from skillbom.rules import Policy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/demo"
ORG = "Acme Analytics (sample)"

MIT = ("MIT License\n\nCopyright (c) 2026 {who}\n\nPermission is hereby granted, free of charge, to any person "
       "obtaining a copy of this software ...\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND.\n")
APACHE = "                                 Apache License\n                           Version 2.0, January 2004\n"
GPL3 = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n... either version 3 of the License, or (at your option) any later version.\n"
CC_NC = "Attribution-NonCommercial 4.0 International\n\nCreative Commons Corporation ...\n"
POLYFORM_NC = "PolyForm Noncommercial License 1.0.0\n\n<https://polyformproject.org/licenses/noncommercial/1.0.0>\n"
PROPRIETARY = "Copyright (c) 2026 Slidecraft Inc. All rights reserved.\n\nInternal evaluation only.\n"
LEXICON = "Lexicon commercial team license. See https://example.com/terms\n"
CUSTOM = "Datawise Skill License v1\n\nYou may use this skill for up to 30 days per calendar year ...\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def skill(d: Path, name: str, desc: str, license_line: str = "", body: str = "") -> Path:
    write(d / "SKILL.md", f"---\nname: {name}\ndescription: {desc}\n{license_line}---\n\n# {name}\n\n{body or desc}\n")
    return d


def shared_skills(skills: Path) -> None:
    skill(skills / "sql-review", "sql-review", "Review SQL migrations for locking and data-loss risks.", "license: MIT\n")
    skill(skills / "brand-voice", "brand-voice", "Rewrite copy in the company's brand voice.")


def contract_check(d: Path, modified: bool = False) -> Path:
    body = "Check B2B contracts against a clause checklist." + (" Also flags auto-renewal terms." if modified else "")
    return skill(d, "contract-check", "Check contracts against a clause checklist.", body=body)


def contract_license(d: Path, digest: str) -> None:
    write(d / "skill-license.yaml", f"""specVersion: "0.1"
subject: {{kind: skill, id: lexicon/contract-check, version: 2.1.0, contentHash: {{alg: sha256, value: "{digest}"}}}}
licensors: [{{name: Lexicon Legal Tools, role: publisher}}]
license:
  expression: LicenseRef-commercial-team
  text: LICENSE.md
  offers:
    - id: LicenseRef-commercial-team
      scope: {{licensee: team, seats: 10}}
      term: {{type: subscription, durationDays: 365}}
      grants: {{internalUse: true, commercialUse: true, modify: false, compose: none}}
""")
    write(d / "LICENSE.md", LEXICON)


def devtools_plugin(home: Path) -> None:
    plugin = home / ".claude/plugins/cache/acme-internal/devtools/1.4.0"
    write(plugin / ".claude-plugin/plugin.json", json.dumps(
        {"name": "devtools", "version": "1.4.0", "author": {"name": "Acme Platform Team"}, "license": "MIT"}))
    write(plugin / "LICENSE", MIT.format(who="Acme Analytics"))
    skill(plugin / "skills/test-writer", "test-writer", "Write unit tests for the selected code.")
    skill(plugin / "skills/api-docs", "api-docs", "Generate API reference docs from source.")
    write(home / ".claude/plugins/installed_plugins.json", json.dumps(
        {"version": 2, "plugins": {"devtools@acme-internal": [{"scope": "managed", "installPath": str(plugin)}]}}))


def laptop_01(home: Path, contract_digest: str) -> None:
    s = home / ".claude/skills"
    shared_skills(s)
    devtools_plugin(home)
    contract_license(contract_check(s / "contract-check"), contract_digest)
    write(skill(s / "pdf-forms", "pdf-forms", "Fill and validate PDF forms.") / "LICENSE", APACHE)
    skill(s / "release-notes", "release-notes", "Draft release notes from merged changes.", "license: Apache-2.0\n")
    write(skill(s / "market-research", "market-research", "Summarize competitor positioning.") / "LICENSE", CC_NC)
    write(skill(s / "slide-builder", "slide-builder", "Build slide decks in the corporate template.",
                "license: Proprietary. See LICENSE.txt\n") / "LICENSE.txt", PROPRIETARY)


def laptop_02(home: Path, contract_digest: str) -> None:
    s = home / ".claude/skills"
    shared_skills(s)
    devtools_plugin(home)
    # A locally edited copy: its content no longer matches the declared hash.
    contract_license(contract_check(s / "contract-check", modified=True), contract_digest)
    write(skill(s / "code-tour", "code-tour", "Walk a newcomer through a codebase.") / "LICENSE", POLYFORM_NC)
    write(skill(s / "data-cleaner", "data-cleaner", "Normalize messy CSV exports.") / "LICENSE", CUSTOM)


def build_01(home: Path) -> None:
    s = home / ".claude/skills"
    shared_skills(s)
    write(skill(s / "legacy-helper", "legacy-helper", "Port legacy scripts to the current toolchain.") / "LICENSE", GPL3)


def main() -> None:
    policy = Policy(id="acme-skill-policy", version="2026-10", denied=["GPL-*", "AGPL-*"])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        original = contract_check(tmp / "original")
        write(original / "LICENSE.md", LEXICON)  # part of the hashed content; skill-license.yaml is not
        digest = content_hash(original)
        boms = []
        for host, make in (("laptop-01", lambda h: laptop_01(h, digest)),
                           ("laptop-02", lambda h: laptop_02(h, digest)),
                           ("build-01", build_01)):
            home = tmp / host
            make(home)
            cands = discover.claude_code(home)
            boms.append(build(cands, roots=[home / ".claude"], policy=policy, home=home, host=host, organization=ORG))
        bom = merge(boms)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "skillbom.json").write_text(json.dumps(bom, indent=2) + "\n")
    (OUT / "report.html").write_text(render(bom, title=f"Skill license audit — {ORG}"))
    s = bom["summary"]
    print(f"{s['components']} components on {s['hosts']} hosts, findings: "
          + ", ".join(f"{k} {v}" for k, v in s["findingsBySeverity"].items() if v))


if __name__ == "__main__":
    main()
