# skillbom scanner reference

**Version:** skillbom 0.1.0 · **Updated:** 2026-10-23 · **Source:** [`plugins/skillbom/src/skillbom/`](https://github.com/eukgoekoko/skillbom/tree/main/plugins/skillbom/src/skillbom)

How the reference scanner finds skills, works out their licenses and fills in a [Skill BOM](skill-bom.md). The format itself is tool-neutral; this page describes one implementation of it.

## Usage

```sh
skillbom scan -o bom.json --html report.html         # this machine
skillbom scan --policy policy.yaml                   # apply allowed/denied licenses
skillbom scan --include-catalogs                     # also plugins available in marketplaces
skillbom scan --no-home --root DIR                   # only DIR
skillbom scan --host-id laptop-anna                  # your own machine name
skillbom merge a.json b.json -o all.json --html all.html
skillbom report bom.json -o report.html
```

In Claude Code, the `skillbom` plugin runs the same scanner through `/skillbom:audit`.

## Where it looks

| runtime | locations | `installScope` |
|---|---|---|
| Claude Code | `~/.claude/skills/*/` | `user` |
| | `~/.claude/skills/synced/<org>_<account>/*/` (skills synced from claude.ai) | `user` |
| | installed plugins from `~/.claude/plugins/installed_plugins.json` (falling back to `plugins/cache/`), with `enabled` from `settings.json` → `enabledPlugins` | as installed |
| Claude Code, managed | `/Library/Application Support/ClaudeCode` (macOS), `/etc/claude-code` (Linux), scanned recursively | `managed` |
| Codex CLI | `$CODEX_HOME/skills` or `~/.codex/skills` | `user` |
| Projects (`--project DIR`) | `DIR/.claude/skills/*/`, `DIR/.codex/skills/*/` | `project` |
| Anything else (`--root DIR`) | recursively: a directory with `.claude-plugin/plugin.json` is a plugin; one with `SKILL.md` is a skill | `local` |
| Catalogs (`--include-catalogs`) | plugins that marketplace clones in `~/.claude/plugins/marketplaces/*` ship locally | `catalog` |

Skills under a plugin's `skills/*/` become separate components (`installScope: plugin`) with a `contains` dependency from the plugin.

Components are deduplicated by content hash. `bomRef` is `<kind>-<first 12 hex of the hash>`, which stays the same across scans and machines. When the same content appears in several places, the license detected at the first occurrence is kept.

## License detection

Every source consulted is recorded as `evidence`, with a confidence:

| source | where | confidence |
|---|---|---|
| `skill-license-file` | `skill-license.yaml` in the component directory | 1.0 |
| `plugin-manifest` | `license` in the component's own `.claude-plugin/plugin.json` or `package.json` | 0.9 if valid SPDX |
| `skill-frontmatter` | `license:` in the SKILL.md frontmatter | 0.9 if valid SPDX |
| `skill-body` | the first line under a `## License` heading in the SKILL.md body | ≤ 0.8 |
| `text-match` | LICENSE/COPYING files in the component directory, or a file a declared value names ("SEE LICENSE IN …", "terms in LICENSE.txt") | 0.9 (GNU licenses 0.85); "all rights reserved" or "proprietary" text → `LicenseRef-proprietary` at 0.5 |
| `parent-manifest` | `license` in a `.claude-plugin/plugin.json` or `package.json` of a parent directory | declared value × 0.8 |
| `repo-license-file` | license files in a parent directory | text-match × 0.8 |
| `marketplace-metadata` | `license` in the catalog's `marketplace.json` entry | ≤ 0.7 |

**Parent directories** are searched from the nearest upward, up to the scan boundary (the marketplace clone, project root or scan root). The first level that declares anything wins, and at that level a manifest is preferred over a license file. A plugin that declares MIT inside an AGPL repository is therefore MIT.

**License texts** are identified in this order:
1. GNU licenses by their heading. The GPL-3.0 text mentions the AGPL in its section 13, so phrase matching would misfire. `-or-later` is reported only when an "any later version" notice appears before the license's own "How to Apply" appendix.
2. A recognized title line ("MIT License", "PolyForm Noncommercial License 1.0.0"): 0.9 when the license's key phrases confirm it, 0.6 otherwise (pointer texts such as "MIT License – see repository root LICENSE").
3. Key phrases anywhere in the text.
4. Otherwise `LicenseRef-custom` at 0.3: a license exists, but it isn't one the scanner knows.

**Declared values** that aren't valid SPDX are parsed in three steps:
1. Free-text license names ("BSD-3-Clause license", "GPLv3", "MIT + Commons Clause", Creative Commons URLs, npm's `UNLICENSED`) resolve through the `names` table in [`spdx-grants.yaml`](https://github.com/eukgoekoko/skillbom/blob/main/plugins/skillbom/src/skillbom/data/spdx-grants.yaml), at 0.8.
2. Otherwise, a value mentioning "proprietary" resolves to `LicenseRef-proprietary` at 0.6.
3. Any license file the value names is followed.

**Resolution.** Evidence from the component itself always beats inherited evidence, whatever the confidence: a plugin's own LICENSE overrides the license of the repository it sits in. Inherited evidence is used only when the component itself says nothing. Within each tier, the highest confidence wins, with ties broken in the table's order.

**Accuracy.** On a held-out sample of 100 public skills, detection matched hand labels on every unambiguous case. Method and results are in the [corpus study](research/corpus-2026-10.md#accuracy).

## Grants for SPDX licenses

To apply the [grant rules](license-file.md#grants) to open-source licenses, the scanner maps SPDX ids to the grant vocabulary in [`spdx-grants.yaml`](https://github.com/eukgoekoko/skillbom/blob/main/plugins/skillbom/src/skillbom/data/spdx-grants.yaml). The mapping covers the common permissive, copyleft, Creative Commons and source-available licenses (PolyForm, BUSL, Elastic, FSL, SSPL, Commons Clause). It is a tooling summary, not legal advice, and it needs review by someone with a legal background.

## Merging scans

`skillbom merge` combines per-machine BOMs:
- **Components** line up across machines because `bomRef` comes from the content hash. Their installations are combined.
- **Conflicting detections:** when machines detect different licenses for the same content (for example, one copy sits in a repository with a LICENSE and another doesn't), the stronger status wins (declared > inferred > unknown), then the higher confidence. License findings are taken only from the scan whose detection won, so stale findings from a weaker scan are dropped. Other findings are deduplicated.
- **Policies:** if the inputs used different policies, the CLI warns and the merged BOM records none.

## Policies

A policy is a YAML file passed with `--policy`:

```yaml
id: acme-skill-policy
version: "2026-09"
allowedLicenses: [MIT, Apache-2.0, BSD-*, "LicenseRef-*"]   # fnmatch globs; empty = allow all
deniedLicenses: [GPL-*, AGPL-*]                                # wins over allowed
severities: {license-unknown: high}                            # override default severities
```

## Rules: implementation status

| rule | status |
|---|---|
| `license-denied`, `commercial-use-restricted`, `license-unknown`, `license-invalid`, `license-review`, `license-conflict`, `integrity-modified` | implemented |
| `composition-incompatible` | implemented for SPDX licenses with a grant mapping; `LicenseRef-` components need purchase records |
| `entitlement-missing`, `entitlement-insufficient`, `entitlement-expired` | need a purchase registry, which doesn't exist yet |
| `obligation-unmet` | not yet |

Without purchase records, `entitlement.status` is `not-required` when some license choice permits commercial use, and `unknown` otherwise.

## Privacy

The scanner runs locally and uploads nothing. Host ids default to a pseudonymous hash of machine and user name, and paths under the home directory are written as `~`. See the [privacy statement](privacy.md).

## Known limitations

- **Plugin copies don't inherit their repository's LICENSE.** An installed plugin's copy lives outside its marketplace clone, so it doesn't inherit the clone's root LICENSE, while the catalog copy does.
- **Only files the scanner knows are read.** License statements in READMEs or source-file headers aren't considered.
- **Repos that license docs and code separately** (e.g. `LICENSE` for code and `LICENSE-CONTENT` for docs) are reported as a choice between both licenses.
