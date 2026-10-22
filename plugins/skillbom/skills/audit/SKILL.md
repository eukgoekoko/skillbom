---
name: audit
description: Audit the licenses of the agent skills and plugins installed on this machine and produce a Skill BOM (JSON) plus an HTML audit report. Use when the user asks what licenses their skills or plugins are under, whether they may use installed skills commercially, for a skill/plugin inventory or "SBOM", or runs /skillbom:audit.
---

# Skill license audit

Scan the installed skills and plugins, then report what was found. Everything runs locally and nothing is uploaded; say so if the user asks.

## 1. Run the scanner

The launcher is `bin/skillbom`, two directories above this skill's base directory: `<base>/../../bin/skillbom`. Use its absolute path. Write the output to a timestamped folder in the user's home directory, not to the current project:

```sh
OUT="$HOME/skillbom-reports/$(date +%Y-%m-%d-%H%M)"; mkdir -p "$OUT"
"<base>/../../bin/skillbom" scan -o "$OUT/skillbom.json" --html "$OUT/report.html"
```

Add options only when the user's request calls for them:

| user wants | add |
|---|---|
| this project's skills too | `--project "$PWD"` |
| plugins available in marketplaces but not installed | `--include-catalogs` |
| a policy (allowed/denied licenses) | `--policy FILE` (YAML with `allowedLicenses`, `deniedLicenses`, `severities`) |
| a specific folder of skills | `--root DIR` (add `--no-home` to scan only that folder) |
| their company name on the report | `--organization "NAME"` |

On the first run the launcher may spend a few seconds installing PyYAML into `~/.cache/skillbom`. That's expected.

The scanner prints a summary on stderr: component counts, licenses, and every non-info finding.

## 2. Report back

Keep it short:
- How many skills and plugins, and the license mix.
- Findings by severity. Lead with critical/high, and name the affected components. Group repeated findings ("26 skills from gitnexus are PolyForm Noncommercial") rather than listing each one.
- Where the files are: `$OUT/report.html` and `$OUT/skillbom.json`.

Then offer to open the report (`open` on macOS, `xdg-open` on Linux).

Reading the results:
- **Inferred** licenses come from manifests, SKILL.md frontmatter or LICENSE files. Only a `skill-license.yaml` makes a license **declared**.
- **`LicenseRef-proprietary`** means "All rights reserved" or proprietary terms were detected. **`LicenseRef-custom`** means a license text exists that isn't a known license, so someone has to read it.
- **Entitlement `unknown`** for commercial licenses is normal: there's no purchase registry yet.
- License categories are a summary of the license texts, not legal advice. Say so if the user asks whether they're allowed to do something.

If the user asks about one component, read its entry in `skillbom.json`. It lists every piece of evidence with its file path and confidence.
