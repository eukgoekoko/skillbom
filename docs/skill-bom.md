# Skill BOM report — draft 0.1

Schema: [`schema/skill-bom.schema.json`](https://github.com/eukgoekoko/skillbom/blob/main/schema/skill-bom.schema.json) · Example: [`examples/skill-bom/acme-2026-10.json`](https://github.com/eukgoekoko/skillbom/blob/main/examples/skill-bom/acme-2026-10.json)

The scanner's output is an inventory of every skill and plugin installed across an organization, with license status, purchase coverage and findings. Its shape follows CycloneDX (`components` + `dependencies`), so it can later be exported to CycloneDX or SPDX for tools that already read SBOMs.

## Structure

- **`metadata`**: when the scan ran, which tool produced it, which hosts and directories were scanned, and the org policy that was applied (allowed and denied licenses).
- **`components`**: one entry per distinct content hash. The same skill at the same hash on 50 machines is one component with 50 `installations`. A locally modified copy has a different hash, so it becomes a separate component with `integrity: modified`.
- **`dependencies`**: containment and derivation edges (a plugin contains a skill; one skill is a modified copy of another).
- **`findings`**: rule violations, each pointing at component `bomRef`s.
- **`summary`**: counts for a dashboard.

## Where the scanner looks

Implemented in `plugins/skillbom/src/skillbom/discover.py`:

| runtime | locations |
|---|---|
| Claude Code | `~/.claude/skills/*/` (user), `~/.claude/skills/synced/<org>_<account>/*/` (synced from claude.ai), installed plugins from `~/.claude/plugins/installed_plugins.json` (falling back to `plugins/cache/`), with `enabled` taken from `settings.json` → `enabledPlugins` |
| Claude Code, managed | `/Library/Application Support/ClaudeCode` (macOS), `/etc/claude-code` (Linux), scanned recursively |
| Codex CLI | `$CODEX_HOME/skills` or `~/.codex/skills` |
| Projects (`--project DIR`) | `DIR/.claude/skills/*/`, `DIR/.codex/skills/*/` |
| Anything else (`--root DIR`) | recursive: a directory with `.claude-plugin/plugin.json` is a plugin; one with `SKILL.md` is a skill |
| Catalogs (`--include-catalogs`) | plugins that marketplace clones (`~/.claude/plugins/marketplaces/*`) ship locally, even when not installed |

Skills under a plugin's `skills/*/` become separate components with a `contains` edge from the plugin.

`installScope` records where an installation came from: `managed` (pushed by the org), `user`, `project` (checked into a repo), `plugin` (nested inside a plugin), `local` (`--root`), or `catalog` (available, not installed).

## Merging scans

Each machine runs `skillbom scan` (optionally with `--host-id` to use the organization's own machine names instead of the pseudonymous default), and `skillbom merge` combines the BOMs:

- **Components** line up across hosts because `bomRef` is derived from the content hash. Their installations are unioned.
- **When hosts detect different licenses** for the same content (for example, one copy sits in a repository with a LICENSE and another doesn't), the detection with the stronger status (declared > inferred > unknown) and then the higher confidence is kept. License-derived findings are taken only from the scan whose detection was kept. Other findings are deduplicated.
- **Metadata:** `metadata.mergedFrom` lists the input `serialNumber`s, and `summary.hosts` counts distinct hosts. If the inputs were scanned with different policies, the merged BOM records no policy and the CLI warns.

## License detection

`license.status` is `declared` when the resolved expression comes from a skill-license file, `inferred` when it comes from other evidence, and `unknown` otherwise. Every source the scanner consults is recorded in `evidence`, together with the raw `value` when the declared text isn't a valid SPDX expression.

| source | where | confidence |
|---|---|---|
| `skill-license-file` | `skill-license.yaml` in the component directory | 1.0 |
| `plugin-manifest` | `license` in `.claude-plugin/plugin.json` or `package.json` | 0.9 if valid SPDX |
| `skill-frontmatter` | `license:` in the SKILL.md frontmatter | 0.9 if valid SPDX |
| `text-match` | LICENSE/COPYING files in the component directory, or a file the declared value names ("SEE LICENSE IN …", "terms in LICENSE.txt") | 0.9 (GNU family 0.85); "all rights reserved"/"proprietary" text → `LicenseRef-proprietary` at 0.5 |
| `repo-license-file` | the nearest ancestor directory with a LICENSE, up to the scan boundary (marketplace clone, project root, scan root) | text-match × 0.8 |
| `marketplace-metadata` | `license` in the catalog's `marketplace.json` entry | ≤ 0.7 |

Declared values that aren't SPDX are parsed in three steps:
1. A free-text license name ("BSD-3-Clause license", "GPLv3", "MIT + Commons Clause", Creative Commons URLs, npm's `UNLICENSED`) resolves through the `names` table in `spdx-grants.yaml`, at confidence 0.8.
2. Otherwise, a value mentioning "proprietary" resolves to `LicenseRef-proprietary` at 0.6.
3. Any license file the value names is followed.

License texts that match no fingerprint fall back to their title line ("MIT License – see repository root LICENSE"), at 0.6. If the title doesn't match either, the text resolves to `LicenseRef-custom` at 0.3: a license exists, but it isn't one we know.

**Resolution.** The component's own evidence (the first four sources) always beats inherited evidence (`repo-license-file`, `marketplace-metadata`), because a plugin's own LICENSE overrides the license of the repository it sits in. Inherited evidence is used only when the component itself says nothing. Within a tier, the highest confidence wins, with ties broken in table order.

Content is deduplicated by hash. When the same content shows up in several places, the license detected at the first occurrence is kept. Known limitation: an installed plugin's copy lives outside its marketplace clone, so it doesn't inherit the clone's repo LICENSE, while the catalog copy does.

## Entitlement status

The scanner resolves each non-open component against the purchase registry:

| status | meaning |
|---|---|
| `not-required` | Open license, or the org's own component. |
| `covered` | A valid entitlement covers this use. |
| `insufficient` | An entitlement exists but doesn't cover this use: too few seats, wrong scope, or a missing grant. |
| `missing` | A commercial license is required and none is on record. |
| `unknown` | The license is unknown, so coverage can't be determined. |

## Rule catalog

| rule | default severity | trigger | implemented |
|---|---|---|---|
| `license-denied` | critical | The expression has no choice that the policy allows. | yes |
| `entitlement-missing` | high | A commercial-only license with no entitlement. | needs registry |
| `entitlement-insufficient` | high | Seats exceeded, wrong scope, or a needed grant absent. | needs registry |
| `entitlement-expired` | high | A subscription or fixed term has passed `expires`. | needs registry |
| `commercial-use-restricted` | high | No choice in the expression grants `commercialUse` (e.g. CC-BY-NC-4.0 alone). | yes |
| `composition-incompatible` | high | A plugin's `includes` fails the composition check (see license-file.md). Checked for mapped SPDX licenses; `LicenseRef-` includes need the registry. | partly |
| `license-unknown` | medium | No license evidence at all. | yes |
| `license-invalid` | medium | A skill-license file exists but can't be read or its expression isn't valid SPDX. | yes |
| `license-review` | medium | The license is `LicenseRef-custom`: a license text exists but isn't a known license. | yes |
| `license-conflict` | medium | The component's own evidence resolves to different expressions (confidence ≥ 0.5). | yes |
| `obligation-unmet` | low | An attribution or license file is missing in a bundled copy. | not yet |
| `integrity-modified` | info | The hash differs from the one declared in the skill-license file. | yes |

Severities are defaults. A policy file can override them:

```yaml
id: acme-skill-policy
version: "2026-09"
allowedLicenses: [MIT, Apache-2.0, BSD-*, "LicenseRef-*"]   # fnmatch globs; empty = allow all
deniedLicenses: [GPL-*, AGPL-*]                                # wins over allowed
severities: {license-unknown: high}
```

Entitlement status is `not-required` when some choice grants commercial use. Until a purchase registry exists, everything else is `unknown`.

## Open questions

- Seat counting: by distinct OS user, by Claude account, or by actual invocation (which needs telemetry)?
- Host and user pseudonymization for reports shared with vendors.
- Output formats beyond JSON: an HTML/PDF audit report, and a CycloneDX export mapping.
