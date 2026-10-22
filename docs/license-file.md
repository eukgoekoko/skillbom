# Skill License File — draft 0.1

Schema: [`schema/skill-license.schema.json`](../schema/skill-license.schema.json) · Examples: [`examples/skill-license/`](../examples/skill-license/)

A machine-readable license declaration for an agent skill or plugin. It is meant to be adopted by any catalog or runtime, so nothing in it is specific to Claude Code.

## Placement

- File name: `skill-license.yaml` (or `skill-license.json`).
- Location: the root of the skill directory (next to `SKILL.md`) or of the plugin (next to `.claude-plugin/plugin.json` or the equivalent manifest).
- A plugin's file covers the plugin as a whole. Skills inside it may carry their own files. Those take precedence for that skill and must be listed under `includes` in the plugin's file.

## Semantics

**`license.expression`** is an [SPDX license expression](https://spdx.github.io/spdx-spec/v2.3/SPDX-license-expressions/).
- Open-source licenses use standard SPDX ids (`MIT`, `Apache-2.0`, `CC-BY-4.0`, …).
- Commercial terms use `LicenseRef-<name>` ids. Each one must be defined in `license.offers` and needs a human-readable `license.text`.
- `A OR B` means the licensee picks one. That is how dual licensing works ("free for non-commercial use, paid for commercial use"): see `examples/skill-license/commercial-dual.yaml`.

**`offers[].grants`** follows a default-deny rule: any permission that isn't granted is denied. The machine-readable fields are a summary for tooling, and `termsUrl` or `license.text` is the binding text. If the two disagree, the text wins, and a scanner should report the mismatch.

| grant | meaning |
|---|---|
| `internalUse` | Run the skill inside the licensee's organization. |
| `commercialUse` | Use it in revenue-generating work. |
| `modify` | Change the skill's content. |
| `redistribute` | `none` / `unmodified` / `modified`: hand copies to third parties. |
| `compose` | Bundle it into the licensee's own plugins: `none` / `internal-only` / `redistributable`. |
| `serviceUse` | Power a hosted service offered to others (e.g. a hosted runtime that executes the skill for its users). |

**`includes`** lists the third-party components a plugin or bundle ships or was derived from. It is the input for composition checks (below). `entitlementRef` points to the purchase record that proves the bundler's right to include the component.

## Content hash

`subject.contentHash` lets scanners tell an original from a modified copy. Procedure (draft):

1. Collect every regular file under the subject directory, excluding `.git/` and `node_modules/` directories and `skill-license.*` and `.DS_Store` files at any depth. Symlinks are skipped.
2. Sort the files by their POSIX relative path (byte order).
3. For each file, feed `<relative path>\0<sha256 of file bytes as hex>\n` into the hash.
4. The hex digest of that stream is the value.

Because text files are hashed byte for byte, a CRLF/LF change counts as a modification. That is a deliberate choice for now, and still open.

## Composition check

A plugin P that includes component C with license L passes when **at least one** licensee choice in L permits the use:

| `relation` | required grants in the chosen offer (or open license) |
|---|---|
| `references` | Nothing beyond the user's own entitlement to C. |
| `bundled` | `compose` ≠ `none`. If P is distributed outside the org: `compose = redistributable` and `redistribute` ≠ `none`. |
| `modified` / `derived` | As for `bundled`, plus `modify = true`. If distributed: `redistribute = modified`. |

For SPDX ids, the scanner maps known licenses to the same grant vocabulary (`plugins/skillbom/src/skillbom/data/spdx-grants.yaml`). For example, MIT allows everything, with the `attribution` and `keep-license-file` obligations. Copyleft licenses add a constraint on P's own license, which is checked with the usual SPDX compatibility rules. Open question: legally, whether a "derived" skill (an LLM paraphrase) counts as a derivative work at all depends on jurisdiction. The `relation` field records intent and does not settle that question.

## Open questions

- A registry namespace for `subject.id` (who controls `<publisher>`?) and how it is verified.
- Signing: should the file (or a detached signature) be signed by the publisher so tampering is detectable?
- Review of the SPDX → `grants` table (`plugins/skillbom/src/skillbom/data/spdx-grants.yaml`) by someone with legal background, and mappings for the ids still listed as `unmapped`.
- How runtimes that keep skills outside the filesystem (claude.ai uploads) can expose this file to a scanner.
