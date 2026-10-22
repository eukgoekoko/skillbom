# skillbom

A license compliance layer for agent skills and plugins (`SKILL.md` skills, Claude Code plugins, Codex skills), playing the role FOSSA or Black Duck play for ordinary software.

It has three parts:
- **An open license-file format** (`skill-license.yaml`): machine-readable license terms that sit next to a skill or plugin, with standard SPDX licenses plus commercial offers.
- **A scanner** (`skillbom`): inventories the skills and plugins installed on a machine, detects their licenses, and writes a **Skill BOM** report with findings.
- **Research** on how public skills are licensed today.

Status: draft 0.1 specs and a scanner prototype.

## Install as a Claude Code plugin

This repository is also a plugin marketplace. In Claude Code:

```
/plugin marketplace add eukgoekoko/skillbom
/plugin install skillbom@skillbom
```

Then run `/skillbom:audit`, or just ask "what licenses are my skills under?". The report lands in `~/skillbom-reports/<timestamp>/`. The scanner runs locally and uploads nothing. It needs Python 3.9 or newer; on first run the launcher installs PyYAML into `~/.cache/skillbom` unless a Python with PyYAML or `uv` is already available.

## Quickstart (development)

Requires Python 3.9+.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/skillbom scan -o bom.json                  # scan this machine; summary on stderr
.venv/bin/skillbom scan --include-catalogs           # also plugins available in marketplace clones
.venv/bin/skillbom scan --no-home --root DIR         # scan only DIR
.venv/bin/skillbom scan --policy policy.yaml         # apply allowed/denied licenses
.venv/bin/skillbom scan -o bom.json --html report.html   # plus an HTML audit report
.venv/bin/skillbom report bom.json -o report.html    # render an existing BOM
.venv/bin/skillbom merge a.json b.json -o all.json --html all.html   # combine scans from several machines
.venv/bin/pytest                                     # tests
```

The scanner looks in `~/.claude` (user skills, skills synced from claude.ai, installed plugins), `~/.codex`, managed install locations, and any `--project` or `--root` directories.

## Repository layout

| path | contents |
|---|---|
| `schema/` | JSON Schemas for the license file and the Skill BOM |
| `docs/license-file.md` | License-file spec: semantics, content hash, composition check |
| `docs/skill-bom.md` | BOM spec: detection sources and confidences, entitlement statuses, rule catalog |
| `docs/research/` | Corpus study of 1,211 public skill repos (October 2026) |
| `examples/` | Example license files and a sample BOM |
| `.claude-plugin/marketplace.json` | Marketplace manifest listing the `skillbom` plugin |
| `plugins/skillbom/` | The plugin: manifest, `audit` skill, `bin/skillbom` launcher |
| `plugins/skillbom/src/skillbom/` | The scanner; `data/spdx-grants.yaml` maps SPDX ids to license grants |
| `scripts/validate.py` | Validates files against the schemas |
| `scripts/corpus/` | Collect, fetch and analyze public skill repos (data goes to `.corpus/`, not committed) |

## Key finding so far

80.5% of public skills are licensed only through their repository's root LICENSE. When a skill is installed by copying its folder, it arrives without any license. Details are in [`docs/research/corpus-2026-10.md`](docs/research/corpus-2026-10.md).

## License

Apache-2.0; see [LICENSE](LICENSE). This covers the code, the schemas and specs, and the research.
