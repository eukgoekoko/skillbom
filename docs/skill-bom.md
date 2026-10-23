# Skill BOM — draft 0.1

**Status:** draft, open for feedback · **Version:** 0.1 · **Updated:** 2026-10-23 · **Schema:** [`skill-bom.schema.json`](https://github.com/eukgoekoko/skillbom/blob/main/schema/skill-bom.schema.json) · **Feedback:** [open an issue](https://github.com/eukgoekoko/skillbom/issues)

A Skill BOM is a bill of materials for agent skills and plugins: a JSON inventory of every skill and plugin found on one or more machines, with where each came from, the license it is under, the evidence for that license, and any findings a compliance team should act on.

This page specifies the format. How the reference scanner produces it is described separately in the [skillbom scanner reference](scanner.md).

## Why a separate BOM format

Software bills of materials (SBOMs) such as [CycloneDX](https://cyclonedx.org/) and [SPDX](https://spdx.dev/) describe packages and their dependencies. Agent skills raise questions those formats don't model:
- **Where the license came from.** Skill licenses are often inferred from a repository root or a parent plugin rather than declared, so each license needs its evidence and a status.
- **Where it's installed.** The same skill sits on many machines in different scopes: user, project, managed by the organization.
- **Whether the company may use it.** The answer depends on commercial entitlements, not just on the license id.

The Skill BOM keeps CycloneDX's overall shape (`components` plus `dependencies`) and adds those parts, so it can be [mapped to CycloneDX](#mapping-to-cyclonedx) for tools that already read SBOMs.

## Conventions

The key words **MUST**, **MUST NOT**, **SHOULD** and **MAY** are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119). Terms such as *licensee*, *offer* and *entitlement* are defined in the [skill license file specification](license-file.md#conventions).

## Example

A trimmed BOM with one host, one component and one finding:

```json
{
  "bomFormat": "SkillBOM",
  "specVersion": "0.1",
  "serialNumber": "urn:uuid:27ab0c9c-39f6-484f-8be4-d2a5ccff4d2c",
  "metadata": {
    "timestamp": "2026-10-22T23:18:11Z",
    "tool": { "name": "skillbom", "version": "0.1.0" },
    "scope": { "organization": "Acme Analytics", "hosts": [{ "id": "laptop-02", "os": "darwin" }] },
    "policy": { "id": "acme-skill-policy", "deniedLicenses": ["GPL-*", "AGPL-*"] }
  },
  "components": [
    {
      "bomRef": "skill-1f0c7a2e9b41",
      "kind": "skill",
      "name": "code-tour",
      "source": { "type": "local" },
      "contentHash": { "alg": "sha256", "value": "1f0c7a2e9b41d3c0e6a8b5f4c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3" },
      "integrity": "unverified",
      "license": {
        "status": "inferred",
        "expression": "PolyForm-Noncommercial-1.0.0",
        "evidence": [
          { "source": "text-match", "path": "~/.claude/skills/code-tour/LICENSE",
            "expression": "PolyForm-Noncommercial-1.0.0", "confidence": 0.9 }
        ]
      },
      "entitlement": { "status": "unknown" },
      "installations": [
        { "host": "laptop-02", "platform": "claude-code", "path": "~/.claude/skills/code-tour", "installScope": "user" }
      ]
    }
  ],
  "findings": [
    {
      "id": "F1",
      "rule": "commercial-use-restricted",
      "severity": "high",
      "components": ["skill-1f0c7a2e9b41"],
      "message": "'code-tour' is licensed PolyForm-Noncommercial-1.0.0, which does not permit commercial use.",
      "remediation": "Obtain a commercial license from the author or stop using it for work."
    }
  ],
  "summary": {
    "components": 1,
    "installations": 1,
    "hosts": 1,
    "byLicenseStatus": { "declared": 0, "inferred": 1, "unknown": 0 },
    "findingsBySeverity": { "critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0 }
  }
}
```

A complete BOM merged from three machines: [sample report](demo/report.html), [its JSON](demo/skillbom.json).

## Field reference

### Top level

| field | type | required | meaning |
|---|---|---|---|
| `bomFormat` | `"SkillBOM"` | yes | Identifies the format. |
| `specVersion` | string | yes | The version of this specification. For this draft: `"0.1"`. |
| `serialNumber` | string | yes | A unique id for this BOM: `urn:uuid:<uuid>`. |
| `metadata` | object | yes | When, by what and over which scope the BOM was produced. |
| `components` | array | yes | The skills and plugins found. |
| `dependencies` | array | no | Relations between components. |
| `findings` | array | no | Issues found, each pointing at components. |
| `summary` | object | yes | Counts for dashboards. |

### `metadata`

| field | type | required | meaning |
|---|---|---|---|
| `timestamp` | date-time | yes | When the BOM was produced (UTC). |
| `tool` | object | yes | `name` and `version` of the producing tool. |
| `scope` | object | yes | `organization` (optional) and `hosts`: what was scanned. |
| `policy` | object | no | The license policy findings were evaluated against: `id`, `version`, `allowedLicenses`, `deniedLicenses`. |
| `mergedFrom` | array of strings | no | The `serialNumber`s of the BOMs this one was merged from. |

Each entry in `scope.hosts`:

| field | type | required | meaning |
|---|---|---|---|
| `id` | string | yes | A host identifier. Producers SHOULD pseudonymize it unless the organization supplies its own names. |
| `os` | string | no | Operating system. |
| `platforms` | array | no | Agent runtimes found on the host, such as `claude-code` or `codex-cli`. |
| `roots` | array | no | Directories that were scanned. |

### `components[]`

One entry per distinct content. The same skill with the same content on 50 machines is **one** component with 50 installations. A locally modified copy has different content, so it is a separate component.

| field | type | required | meaning |
|---|---|---|---|
| `bomRef` | string | yes | Identifier, unique within the BOM. It SHOULD be derived from `kind` and `contentHash`, so the same content gets the same `bomRef` in every BOM. That is what makes BOMs mergeable. |
| `kind` | `skill` · `plugin` · `command` · `agent` · `hook` · `mcp-server` · `marketplace` | yes | What the component is. |
| `id` | string | no | `<publisher>/<name>`, from the component's skill license file, if it has one. |
| `name` | string | yes | Display name. |
| `version` | string | no | Version, if declared. |
| `publisher` | string | no | Author or publisher, if declared. |
| `source` | object | yes | Where it came from: `type` (`marketplace`, `git`, `registry`, `local` or `unknown`), plus optional `marketplace`, `url` and `ref`. |
| `contentHash` | object | yes | Computed as in the [license file specification](license-file.md#content-hash). |
| `integrity` | `match` · `modified` · `unverified` | no | Whether `contentHash` matches the hash declared in the component's skill license file, or `unverified` if none is declared. |
| `license` | object | yes | See below. |
| `entitlement` | object | no | See below. |
| `installations` | array | yes | Where it is installed. See below. |

`license`:

| field | type | required | meaning |
|---|---|---|---|
| `status` | `declared` · `inferred` · `unknown` | yes | `declared`: taken from a skill license file. `inferred`: from other evidence. `unknown`: no license found. |
| `expression` | string | yes | An SPDX expression, or `NOASSERTION` when unknown. |
| `evidence` | array | no | Every piece of evidence the producer considered, including evidence that lost. Each entry has `source` (required), and optionally `path`, `expression`, `confidence` (0–1) and `value`, the raw declared text when it isn't valid SPDX. |

Evidence `source` values: `skill-license-file`, `plugin-manifest`, `skill-frontmatter`, `skill-body` and `text-match` are evidence from the component itself; `parent-manifest`, `repo-license-file` and `marketplace-metadata` are evidence it inherits from its surroundings.

Producers use three `LicenseRef-` ids with fixed meanings:

| id | meaning |
|---|---|
| `LicenseRef-proprietary` | "All rights reserved" or explicitly proprietary terms were found. |
| `LicenseRef-custom` | A license text exists but doesn't match a known license; a human needs to read it. |
| `LicenseRef-commons-clause` | The Commons Clause, combined with its base license, e.g. `Apache-2.0 AND LicenseRef-commons-clause`. |

`entitlement`:

| field | type | required | meaning |
|---|---|---|---|
| `status` | see below | yes | Whether the organization may use the component as installed. |
| `registryRef`, `offer` | string | no | The purchase record and the `LicenseRef-` offer it covers. |
| `seatsLicensed`, `seatsInUse` | integer | no | For seat-based offers. |
| `expires` | date | no | When the entitlement ends. |

| status | meaning |
|---|---|
| `not-required` | An open license permits commercial use, or the component is the organization's own. |
| `covered` | A valid entitlement covers this use. |
| `insufficient` | An entitlement exists but doesn't cover this use: too few seats, the wrong scope, or a missing grant. |
| `missing` | A commercial license is required and none is on record. |
| `unknown` | Coverage can't be determined, for example because the license is unknown or no purchase records are available. |

Each entry in `installations`:

| field | type | required | meaning |
|---|---|---|---|
| `host` | string | yes | A `metadata.scope.hosts[].id`. |
| `path` | string | yes | Install location. Producers SHOULD write paths under the user's home directory as `~/…`. |
| `installScope` | see below | yes | How the component got there. |
| `platform` | string | no | The agent runtime it belongs to. |
| `enabled` | boolean | no | Whether the runtime has it enabled, where that is known. |

| `installScope` | meaning |
|---|---|
| `managed` | Deployed by the organization. |
| `user` | Installed by the user for themselves. |
| `project` | Checked into a project repository. |
| `plugin` | Nested inside an installed plugin. |
| `local` | Found in a directory the scan was pointed at. |
| `catalog` | Available in a downloaded marketplace catalog, but not installed. |

### `dependencies[]`

| field | type | required | meaning |
|---|---|---|---|
| `ref` | string | yes | A `bomRef`. |
| `dependsOn` | array of strings | yes | The `bomRef`s it relates to. |
| `relation` | `contains` · `modified` · `derived` · `references` | no | E.g. a plugin `contains` its skills. |

### `findings[]`

| field | type | required | meaning |
|---|---|---|---|
| `id` | string | yes | Unique within the BOM, e.g. `F1`. |
| `rule` | string | yes | A rule id from the [rule catalog](#rule-catalog). |
| `severity` | `critical` · `high` · `medium` · `low` · `info` | yes | How urgent it is. |
| `components` | array of strings | yes | The affected `bomRef`s. |
| `message` | string | yes | A human-readable description. |
| `remediation` | string | no | What to do about it. |

### `summary`

| field | type | required | meaning |
|---|---|---|---|
| `components` | integer | yes | Number of components. |
| `installations` | integer | no | Number of installations across all components. |
| `hosts` | integer | no | Number of distinct hosts with at least one installation. |
| `byKind`, `byLicense`, `byEntitlement` | objects | no | Counts per kind, per license expression and per entitlement status. |
| `byLicenseStatus` | object | yes | Counts for `declared`, `inferred` and `unknown`. |
| `findingsBySeverity` | object | yes | Counts per severity. |

## Rule catalog

Producers SHOULD use these rule ids where they apply, so findings mean the same thing across tools. Severities are defaults; an organization's policy MAY override them.

| rule | default severity | raised when |
|---|---|---|
| `license-denied` | critical | No choice in the license expression is allowed by the policy. |
| `entitlement-missing` | high | A commercial-only license with no entitlement on record. |
| `entitlement-insufficient` | high | An entitlement exists but doesn't cover the use: seats, scope or a needed grant. |
| `entitlement-expired` | high | A subscription or fixed term has ended. |
| `commercial-use-restricted` | high | No choice in the expression permits commercial use, e.g. `CC-BY-NC-4.0` alone. |
| `composition-incompatible` | high | A plugin's `includes` fails the [composition check](license-file.md#composition). |
| `license-unknown` | medium | No license evidence at all. |
| `license-invalid` | medium | A skill license file exists but can't be read, or isn't valid. |
| `license-review` | medium | The license is `LicenseRef-custom` and needs a human to read it. |
| `license-conflict` | medium | The component's own evidence points to different licenses. |
| `obligation-unmet` | low | A bundled copy is missing a required attribution or license file. |
| `integrity-modified` | info | The content doesn't match the hash declared in the skill license file. |

## Merging

A BOM MAY be merged from per-machine BOMs. A merged BOM:
- MUST contain each content once, with the installations of all inputs.
- MUST list its inputs in `metadata.mergedFrom`.
- MUST NOT record a `policy` if its inputs were evaluated against different policies.

How conflicting license evidence across machines is resolved is up to the producer; the reference scanner's approach is described [in its reference](scanner.md#merging-scans).

## Mapping to CycloneDX

*Proposed; not yet implemented as an export.* A Skill BOM maps onto [CycloneDX 1.6](https://cyclonedx.org/docs/1.6/json/) as follows:

| Skill BOM | CycloneDX |
|---|---|
| `bomFormat`, `specVersion` | `bomFormat: "CycloneDX"`, `specVersion: "1.6"` |
| `serialNumber` | `serialNumber` |
| `metadata.timestamp`, `metadata.tool` | `metadata.timestamp`, `metadata.tools.components[]` |
| component `bomRef`, `name`, `version`, `publisher` | component `bom-ref`, `name`, `version`, `publisher` |
| component `kind` | `type: "application"`, plus property `skillbom:kind` |
| `contentHash` | `hashes: [{ alg: "SHA-256", content }]` |
| `license.expression` | `licenses: [{ expression }]` |
| `source.url`, `source.ref` | `externalReferences: [{ type: "vcs", url }]` |
| `license.status`, `evidence`, `integrity`, `entitlement`, `installations` | properties in the `skillbom:` namespace |
| `dependencies` | `dependencies` |
| `findings` | `annotations`, with the affected components as `subjects` |

## Conformance

**A conforming BOM:**
- MUST validate against the [JSON Schema](https://github.com/eukgoekoko/skillbom/blob/main/schema/skill-bom.schema.json) for its `specVersion`.
- MUST give every `bomRef` referenced by `dependencies` or `findings` a matching component.
- MUST record every piece of license evidence it relied on in `evidence`.

**A conforming producer:**
- MUST NOT mark a license `declared` unless it comes from a skill license file.
- SHOULD pseudonymize host ids and shorten home-directory paths to `~`, so BOMs can be shared without exposing user names.

**A conforming consumer:**
- MUST treat license categories and findings as a summary of license texts, not as legal advice.

## Privacy

A BOM describes machines and what is installed on them. It contains file paths, host identifiers, publisher names and license evidence. Producers SHOULD keep it local by default; an organization decides whether and with whom to share it.

## Versioning

Same scheme as the [license file](license-file.md#versioning): `MAJOR.MINOR`. 0.x drafts may change incompatibly; from 1.0 on, minor versions only add optional fields.

## Open questions

- **Seat counting:** by distinct OS user, by agent account, or by actual use (which would need telemetry)?
- **Sharing:** how should BOMs be pseudonymized when they are shared with vendors?
- **Exports:** a CycloneDX export implementing the mapping above, and an SPDX one.

Comments are welcome [as GitHub issues](https://github.com/eukgoekoko/skillbom/issues).

## Changelog

- **2026-10-23:** Split into this format specification and the [scanner reference](scanner.md). Added a field reference, an inline example, `LicenseRef-` ids with fixed meanings, conformance, privacy, versioning and a proposed CycloneDX mapping. No format changes.
- **2026-10-22:** Draft 0.1.
