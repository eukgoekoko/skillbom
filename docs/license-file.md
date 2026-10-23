# Skill License File — draft 0.1

**Status:** draft, open for feedback · **Version:** 0.1 · **Updated:** 2026-10-23 · **Schema:** [`skill-license.schema.json`](https://github.com/eukgoekoko/skillbom/blob/main/schema/skill-license.schema.json) · **Feedback:** [open an issue](https://github.com/eukgoekoko/skillbom/issues)

A skill license file is a small YAML or JSON file that travels inside an agent skill or plugin and states, in machine-readable form, under which terms it may be used. It works with any agent runtime or catalog; nothing in it is specific to Claude Code.

## Why a license file for skills

Agent skills (`SKILL.md` folders) and plugins are installed by copying a folder. Their license usually stays behind at the root of the repository they came from. In our [scan of 62,704 public skills](research/corpus-2026-10.md), 81% carried no license of their own. Where skills do declare something, it is a free-text `license:` line ("Proprietary. LICENSE.txt has complete terms") that tools can't interpret reliably.

A file next to `SKILL.md` fixes the first problem. A precise format fixes the second, and adds what companies need to use a skill at work:

- **Machine-readable terms:** an SPDX license, or commercial offers that say what is permitted (commercial use, modification, bundling, hosted use) and for whom (team, organization, seats).
- **A content hash,** so a modified copy can be told apart from the original.
- **The components a plugin bundles,** so license compatibility can be checked when plugins are assembled from other people's skills.

## Conventions

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

| term | meaning |
|---|---|
| **subject** | The skill, plugin or bundle the file describes. |
| **licensor** | Whoever grants the license: the author or publisher. |
| **licensee** | Whoever uses the subject under the license. |
| **offer** | One commercial variant of the license, identified by a `LicenseRef-` id. |
| **grant** | A permission an offer gives, such as `commercialUse` or `modify`. |
| **obligation** | A duty the licensee takes on, such as attribution. |
| **entitlement** | Proof that a licensee holds an offer, such as a purchase record. Entitlements live outside this file. |
| **producer** | A tool or person that writes skill license files. |
| **consumer** | A tool that reads them: a scanner, catalog or runtime. |

## Placement

- **Name.** The file MUST be named `skill-license.yaml`, `skill-license.yml` or `skill-license.json`. A directory SHOULD contain only one of them. If it contains more than one, consumers SHOULD use the YAML file and report the duplicate.
- **Location.** The file MUST be placed in the subject's root directory: next to `SKILL.md` for a skill, or next to `.claude-plugin/plugin.json` (or the runtime's equivalent manifest) for a plugin.
- **Nesting.** A plugin's file covers the plugin as a whole. A skill inside a plugin MAY carry its own file, which takes precedence for that skill. The plugin's file SHOULD then list that skill under `includes`.

## Example

A skill that is free for non-commercial use, with two commercial offers:

```yaml
specVersion: "0.1"
subject:
  kind: skill
  id: lexwerk/contract-review
  name: Contract Review (DE/EN)
  version: 1.2.0
  contentHash:
    alg: sha256
    value: 8f46f87124f4cad3e3789e4e4a7b8c1caa0aa14d6ac6f34a8a9e3a16e4463688
licensors:
  - name: Lexwerk GmbH
    role: publisher
license:
  expression: CC-BY-NC-4.0 OR LicenseRef-commercial-team OR LicenseRef-commercial-org
  text: LICENSE.md
  offers:
    - id: LicenseRef-commercial-team
      title: Team license
      scope: { licensee: team, seats: 10 }
      term: { type: subscription, durationDays: 365 }
      grants: { modify: true, compose: internal-only }
      obligations: [keep-license-file]
      price: { amount: 49, currency: EUR, per: year-seat }
      termsUrl: https://lexwerk.example/terms/team-1.0
    - id: LicenseRef-commercial-org
      title: Organization license
      scope: { licensee: organization, affiliatesIncluded: true }
      term: { type: perpetual, updatesIncludedDays: 365 }
      grants: { modify: true, redistribute: modified, compose: redistributable, serviceUse: true }
      obligations: [attribution, keep-license-file]
      termsUrl: https://lexwerk.example/terms/org-1.0
```

A skill under a plain open-source license needs only this:

```yaml
specVersion: "0.1"
subject: { kind: skill, id: jdoe/pdf-tools, version: 2.0.1 }
license: { expression: MIT, text: LICENSE }
```

More examples: [`examples/skill-license/`](https://github.com/eukgoekoko/skillbom/tree/main/examples/skill-license).

## Field reference

### Top level

| field | type | required | meaning |
|---|---|---|---|
| `specVersion` | string | yes | The version of this specification the file follows. For this draft: `"0.1"`. |
| `subject` | object | yes | What the file describes. |
| `licensors` | array of objects | no | Who grants the license. |
| `license` | object | yes | The license terms. |
| `includes` | array of objects | no | Third-party components the subject bundles or derives from. |
| `attribution` | string | no | An attribution notice that MUST be preserved when the attribution obligation applies. |

### `subject`

| field | type | required | meaning |
|---|---|---|---|
| `kind` | `skill` · `plugin` · `bundle` | yes | The kind of subject. |
| `id` | string | yes | A stable identifier, `<publisher>/<name>`: lowercase letters, digits and `-`, with `.` and `_` also allowed in the name. |
| `version` | string | yes | A semantic version, e.g. `1.2.0`. |
| `name` | string | no | A display name. |
| `description` | string | no | One line on what the subject does. |
| `homepage` | URL | no | The subject's homepage. |
| `source` | object | no | Where the original lives: `repository` (URL), `ref` (tag or commit) and `path` (directory inside the repository). |
| `contentHash` | object | no | `alg` (`sha256` or `sha512`) and `value` (lowercase hex), computed as described in [Content hash](#content-hash). |
| `platforms` | array of strings | no | Runtimes the subject is meant for, e.g. `claude-code`, `codex-cli`, `cursor`. Informational only. |

### `licensors[]`

| field | type | required | meaning |
|---|---|---|---|
| `name` | string | yes | Person or organization. |
| `email` | string | no | Contact address. |
| `url` | URL | no | Website. |
| `role` | `author` · `publisher` · `contributor` | no | Relationship to the subject. |

### `license`

| field | type | required | meaning |
|---|---|---|---|
| `expression` | string | yes | An [SPDX license expression](https://spdx.github.io/spdx-spec/v2.3/SPDX-license-expressions/). |
| `text` | string | when `expression` uses `LicenseRef-` | Relative path or URL of the full, human-readable license text. |
| `offers` | array of offers | when `expression` uses `LicenseRef-` | Definitions of the `LicenseRef-` ids used in `expression`. |

### `offers[]`

| field | type | required | meaning |
|---|---|---|---|
| `id` | string | yes | `LicenseRef-<name>`, the id used in `expression`. |
| `title` | string | no | A display name for the offer. |
| `scope` | object | yes | Who may use the subject. See below. |
| `term` | object | yes | For how long. See below. |
| `grants` | object | yes | What is permitted. See [Grants](#grants). |
| `obligations` | array | no | Any of `attribution`, `keep-license-file`, `disclose-modifications`, `report-usage`. |
| `price` | object | no | Informational list price: `amount`, `currency` (ISO 4217), `per` (`license`, `seat`, `month-seat`, `year-seat`, `month`, `year`). The binding price is the seller's. |
| `purchaseUrl` | URL | no | Where to buy. |
| `termsUrl` | URL | no | The binding terms of this offer. |

`scope`:

| field | type | required | meaning |
|---|---|---|---|
| `licensee` | `individual` · `team` · `organization` · `enterprise` | yes | The kind of licensee. |
| `seats` | integer ≥ 1 | no | Maximum number of users. Omitted means unlimited within the licensee. |
| `affiliatesIncluded` | boolean | no | Whether affiliated companies are covered. Default `false`. |
| `territory` | array of ISO 3166-1 alpha-2 codes | no | Where the license applies. Omitted means worldwide. |

`term`:

| field | type | required | meaning |
|---|---|---|---|
| `type` | `perpetual` · `subscription` · `fixed` | yes | The kind of term. |
| `durationDays` | integer | for `subscription` and `fixed` | Length of the term. |
| `updatesIncludedDays` | integer | no | For perpetual licenses: how long new versions are covered. |

### `includes[]`

| field | type | required | meaning |
|---|---|---|---|
| `id` | string | yes | The component's `<publisher>/<name>`. |
| `version` | string | yes | The component's version. |
| `license` | string | yes | The SPDX expression under which it is included, often one choice from the component's own expression. |
| `relation` | `bundled` · `modified` · `derived` · `references` | yes | Shipped unchanged, shipped with changes, rewritten or adapted from, or only invoked and not shipped. |
| `entitlementRef` | string | no | Reference to the purchase record that permits including it. |
| `contentHash` | object | no | The hash of the included copy. |

## Semantics

### License expression

- **Ids.** Open-source licenses MUST use standard [SPDX license ids](https://spdx.org/licenses/), such as `MIT`, `Apache-2.0` or `CC-BY-4.0`.
- **Offers.** Every `LicenseRef-` id in `expression` MUST be defined in `license.offers`, and `license.text` MUST be present.
- **Choices.** `A OR B` means the licensee chooses one of the alternatives. This is how dual licensing is expressed: free for non-commercial use, paid for commercial use.
- **Combinations.** `A AND B` means both apply at once.

### Grants

Each offer's `grants` states what the licensee may do:

| grant | type | default | permits |
|---|---|---|---|
| `internalUse` | boolean | `true` | Running the subject inside the licensee's organization. |
| `commercialUse` | boolean | `true` | Using it in work that earns the licensee revenue. |
| `modify` | boolean | `false` | Changing the subject's content. |
| `redistribute` | `none` · `unmodified` · `modified` | `none` | Handing copies to third parties. |
| `compose` | `none` · `internal-only` · `redistributable` | `none` | Bundling it into the licensee's own plugins. |
| `serviceUse` | boolean | `false` | Powering a hosted service offered to others, such as a runtime that executes the skill for its users. |

An offer always permits *using* the subject, so `internalUse` and `commercialUse` default to `true`. Every other grant defaults to its most restrictive value. A grant that isn't stated is therefore never broader than its default, and a consumer MUST NOT assume a permission beyond the defaults.

**The license text is binding.** The grants are a machine-readable summary for tools. When they disagree with `termsUrl` or `license.text`, the text wins, and consumers SHOULD report the mismatch.

For licenses identified by SPDX id, consumers map the license to the same grant vocabulary to apply these rules. MIT, for example, grants everything, with the `attribution` and `keep-license-file` obligations. The [skillbom scanner](scanner.md#grants-for-spdx-licenses) ships a reference mapping.

### Composition

A plugin P that lists component C with license L in `includes` is compatible when **at least one** choice in L permits the relation:

| `relation` | the chosen license must grant |
|---|---|
| `references` | Nothing beyond each user's own right to use C. |
| `bundled` | `compose` other than `none`. If P is distributed outside the licensee's organization: `compose: redistributable` and `redistribute` other than `none`. |
| `modified`, `derived` | As for `bundled`, plus `modify: true`. If distributed: `redistribute: modified`. |

Copyleft licenses additionally constrain P's own license; those constraints follow the usual SPDX compatibility rules.

Whether a "derived" skill, such as an LLM paraphrase of another skill, is a derivative work in the legal sense depends on jurisdiction. The `relation` field records what the producer did; it doesn't settle that question.

## Content hash

`subject.contentHash` lets a consumer tell an original from a modified copy. A producer that sets it MUST compute it as follows:

1. **Collect** every regular file under the subject's root directory. Skip symbolic links, any directory named `.git` or `node_modules`, and any file named `skill-license.yaml`, `skill-license.yml`, `skill-license.json` or `.DS_Store`, at any depth.
2. **Path** each file by its path relative to the root, using `/` as separator, encoded as UTF-8.
3. **Sort** the files by that path, comparing bytes.
4. **Feed** one line per file into a SHA-256 (or SHA-512) hash: the path, a NUL byte, the lowercase hex SHA-256 of the file's bytes, and a newline (`\n`).
5. **Write** the hex digest of that stream as `value`.

File contents are hashed byte for byte, with no line-ending normalization. A copy whose line endings were converted, for example by git's `core.autocrlf` on Windows, therefore counts as modified. Producers SHOULD distribute skills with LF line endings.

**Test vector.** A skill directory containing exactly these two files:

| path | content | SHA-256 of content |
|---|---|---|
| `SKILL.md` | `---\nname: hello\ndescription: Say hello.\n---\n\nSay hello.\n` | `2266d5a037bb13ebcc3c5db01fae36d2915638b7f14f6ac1aed8137698a23a0d` |
| `scripts/greet.py` | `print('hello')\n` | `03e693d9f2f687e0f40e36a8df7fcb4d1c22974012b7c2a55c000eb30f305824` |

has the content hash `a903ec8aa19fa69ad1fc36921aa599b7b924409ee0d8b60d2a07cc09719c74e2`. A `skill-license.yaml` in the same directory doesn't change it. You can reproduce the vector with standard tools:

```sh
printf 'SKILL.md\0%s\nscripts/greet.py\0%s\n' \
  2266d5a037bb13ebcc3c5db01fae36d2915638b7f14f6ac1aed8137698a23a0d \
  03e693d9f2f687e0f40e36a8df7fcb4d1c22974012b7c2a55c000eb30f305824 | shasum -a 256
```

## Conformance

**A conforming file:**

- MUST validate against the [JSON Schema](https://github.com/eukgoekoko/skillbom/blob/main/schema/skill-license.schema.json) for its `specVersion`.
- MUST define every `LicenseRef-` id it uses, and provide `license.text` when it uses any.
- SHOULD include `subject.contentHash` when the subject is distributed.

**A conforming consumer:**

- MUST treat the license text, not the grants, as authoritative.
- MUST NOT treat the file as proof of entitlement. Whether a licensee holds an offer is established by a purchase record, not by the file.
- SHOULD verify `contentHash` when present, and report a mismatch as a modified copy.
- SHOULD report a file it can't parse or validate, rather than silently ignoring it.

## Security and trust

A skill license file is a declaration by whoever wrote it. It is not signed in this version:

- **Authorship is unverified.** Anyone can write a file claiming any license or any `subject.id`. Consumers SHOULD weigh it with the subject's provenance (`subject.source`, the catalog it came from) and SHOULD NOT treat it as verified authorship.
- **Integrity is relative.** `contentHash` shows whether the content matches the file, not whether the file is genuine: someone who changes both can make them agree.
- **No sensitive data.** A file MUST NOT contain secrets, license keys or personal data beyond the licensors' public contact details.

Signing is listed under [open questions](#open-questions).

## Relation to other standards

| standard | what it does | relation to this file |
|---|---|---|
| [SPDX](https://spdx.dev/) | License ids and expressions; documents describing software packages | This file uses SPDX ids and expression syntax unchanged, and adds commercial offers with grants, a skill-level content hash and composition data. |
| [REUSE](https://reuse.software/) | Per-file copyright and license headers plus a `LICENSES/` folder | Works well for open-source repositories, but has no commercial terms. Its information also stays in the repository when a single skill folder is copied out. The two can coexist. |
| [CycloneDX](https://cyclonedx.org/) | Bill-of-materials format | The [Skill BOM](skill-bom.md) report follows CycloneDX's structure; skill license files are one of its inputs. |
| `license:` in SKILL.md frontmatter, `license` in `plugin.json` | A single free-text or SPDX string | Fine for a plain open-source license. When a skill license file exists, it takes precedence, and producers SHOULD keep both consistent. |

## Versioning

`specVersion` has the form `MAJOR.MINOR`.

- **During the 0.x drafts,** any version may change the format incompatibly.
- **From 1.0 on,** a minor version only adds optional fields. Consumers SHOULD accept files with a newer minor version of a major version they support, ignoring fields they don't know.
- **Major versions** may change the format incompatibly. Consumers MUST NOT assume they understand a major version they don't support.

## Open questions

- **Publisher namespace:** who controls `<publisher>` in `subject.id`, and how is that verified?
- **Signing:** should the file, or a detached signature, be signed by the publisher, and with what key infrastructure?
- **Grant mapping review:** the mapping from SPDX ids to grants needs review by someone with a legal background, and mappings for licenses not yet covered.
- **Non-filesystem runtimes:** how can runtimes that keep skills outside the filesystem, such as uploads to a web app, expose this file to a scanner?

Comments on any of these are welcome [as GitHub issues](https://github.com/eukgoekoko/skillbom/issues).

## Changelog

- **2026-10-23:** Editorial rewrite: field reference, conformance, security, relation to other standards, versioning, and a content-hash test vector. Two clarifications: grant defaults (`internalUse` and `commercialUse` default to `true`, everything else to its most restrictive value), and the exact files excluded from the content hash. No format changes.
- **2026-10-22:** Draft 0.1.
