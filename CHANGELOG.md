# Changelog

## 0.2.0 — unreleased

Ships after the Claude plugin directory approves 0.1.1.

**Added**

- **CycloneDX 1.6 export:** `skillbom export BOM`, or `--cyclonedx FILE` on `scan` and `merge`, following the [mapping in the Skill BOM specification](https://eukgoekoko.github.io/skillbom/skill-bom.html#mapping-to-cyclonedx). Installations become `evidence.occurrences` and findings become annotations. Tests validate the output against the official CycloneDX schema.
- **`skillbom init`** for skill authors: writes a `skill-license.yaml` with the id, version, detected license, license text and content hash. `--update` refreshes the hash after edits; `--copy-license` brings an inherited LICENSE into the skill's folder.
- **A `license-file` plugin skill** (`/skillbom:license-file`) that walks authors through `init` in Claude Code.
- **Skills installed with [`npx skills`](https://github.com/vercel-labs/skills):**
  - `~/.agents/skills` is scanned, plus `.agents/skills` in each `--project DIR`.
  - The installer's lock files (global `.skill-lock.json` and project `skills-lock.json`) supply each skill's repository and folder, recorded as `source.url` and the new `source.path`.
  - When no license is found, the finding names the repository to check.

**Security**

- Source URLs from lock files are recorded without credentials or query strings, so a private repository's access token never ends up in a BOM.

## 0.1.1 — 2026-10-23

- **No downloads:** the plugin no longer installs anything at run time. Its only dependency, PyYAML, ships as readable pure-Python source in `vendor/`, and the plugin makes no network requests.
- **New launcher location:** the launcher moved from `bin/` to `scripts/skillbom`.
- **No credential-bearing reads:** the scanner no longer reads `~/.claude/settings.json`, which can hold credentials. As a result, installations no longer carry an `enabled` flag.

## 0.1.0 — 2026-10-22

First release:

- **The scanner:** Claude Code (user, project, managed, synced) and Codex skills and plugins, with license detection from license files, manifests, SKILL.md and LICENSE texts.
- **Reports:** the Skill BOM (JSON) and an HTML audit report.
- **Fleet features:** policies, and `skillbom merge` across machines.
- **The Claude Code plugin** with the `audit` skill.
- **Draft 0.1** of the skill license file and Skill BOM specifications.
