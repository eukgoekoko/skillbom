# skillbom for teams

**Audience:** engineering managers, IT, legal and compliance teams who want to know which AI agent skills are in use across the company, and whether they may be used at work.

If your engineers use coding agents such as Claude Code or Codex, skills and plugins are already on their machines. A [scan of 62,704 public skills](research/corpus-2026-10.md) found that 81% carry no license of their own, and that hundreds don't permit commercial use. This page describes how to get an organization-wide answer in an afternoon.

## How it works

1. **Agree on a policy:** which licenses are fine, and which aren't.
2. **Scan every machine.** skillbom runs locally, takes a few seconds, and writes one JSON file per machine.
3. **Collect the files** the way you collect other inventory data.
4. **Merge them** into one organization-wide Skill BOM and audit report.
5. **Act on the findings.** Each one comes with a suggested fix.
6. **Repeat** monthly, or whenever you roll out new tooling.

Nothing is uploaded anywhere along the way. Every step runs on machines you control.

## 1. Write a policy

A policy is a short YAML file. Licenses are matched with wildcards; denied wins over allowed.

```yaml
id: acme-skill-policy
version: "2026-10"
# Add the commercial LicenseRef-… ids you've bought to the allowed list.
allowedLicenses: [MIT, Apache-2.0, BSD-*, ISC, CC-BY-4.0]
deniedLicenses: [GPL-*, AGPL-*, SSPL-*]
severities:
  license-unknown: high   # unlicensed counts as seriously as restricted
```

Leave `allowedLicenses` empty to allow everything not denied. With a list, anything not on it is flagged, including proprietary and custom terms (`LicenseRef-…`), until legal adds the ones you've licensed. A license outside the policy produces a critical `license-denied` finding. All rule ids and their default severities are in the [rule catalog](skill-bom.md#rule-catalog).

## 2. Scan each machine

**One machine, interactively.** In Claude Code:

```
/plugin marketplace add eukgoekoko/skillbom
/plugin install skillbom@skillbom
/skillbom:audit
```

**Many machines.** Run the command-line scanner through your device management (Jamf, Intune, Kandji, or a configuration-management tool). The scanner reads the **logged-in user's** skills, so it has to run as that user, with that user's home directory (`sudo -H -u`), not as root:

```sh
#!/bin/sh
# Example for macOS device management: scan the console user's skills.
# skillbom installed once per machine, e.g. under /opt/skillbom:
#   git clone https://github.com/eukgoekoko/skillbom /opt/skillbom
#   (pin to a specific commit until releases are tagged)
user=$(stat -f %Su /dev/console)
out="/Users/Shared/skillbom"; mkdir -p "$out"; chmod 1777 "$out"
sudo -H -u "$user" /opt/skillbom/plugins/skillbom/bin/skillbom scan -q \
  --policy /opt/skillbom-policy.yaml \
  --host-id "$(scutil --get ComputerName)" \
  -o "$out/$(scutil --get ComputerName)-$(date +%F).json"
```

- **Requirements:** Python 3.9 or newer. The launcher installs PyYAML once per user, from PyPI, if no Python with PyYAML is available. Pre-install `pyyaml` to avoid that network access.
- **Host ids:** `--host-id` makes reports readable for IT. Without it, each machine gets a pseudonymous id.
- **Project skills:** add `--project DIR` for repositories that ship their own skills. Add `--include-catalogs` to also list plugins that are available in marketplaces but not installed.
- **Platforms:** macOS and Linux are tested. Windows hasn't been tested yet.

## 3. Collect and merge

Collect the JSON files with your device management's file collection, a network share, or your inventory pipeline. Then merge them on any machine:

```sh
skillbom merge reports/*.json --organization "Acme" -o acme-skills.json --html acme-skills.html
```

The merged report lists every distinct skill once, with every machine it's installed on, and a **Hosts** column that shows how widely each one is used. That count is the basis for seat-based licenses. Merging also reconciles machines that saw the same skill differently: the strongest license evidence wins. See [merging scans](scanner.md#merging-scans).

## 4. Act on the findings

The [sample report](demo/report.html) shows what you'll get. Typical findings and who usually acts on them:

| finding | what it means | typical action |
|---|---|---|
| `license-denied` | A skill's license is outside your policy. | Engineering removes or replaces it. |
| `commercial-use-restricted` | A non-commercial license, such as CC-BY-NC or PolyForm Noncommercial. | Buy a commercial license from the author, or remove the skill. |
| `license-unknown` | No license anywhere. By default, nobody may use it. | Ask the author for a license, or remove the skill. |
| `license-review` | A custom license text the scanner doesn't recognize. | Legal reads it once and records the decision. |
| `license-conflict` | A skill's own files disagree about its license. | Ask the author which applies. |
| `integrity-modified` | A copy differs from the version its license file describes. | Check who changed it and whether the license allows that. |

Every finding links to its evidence: which file said what, and with how much confidence. Reviewers can check the reasoning instead of trusting a verdict.

## Privacy

- **Nothing leaves the machine** unless you collect the files yourself.
- **A report contains:** file paths (the home directory is shortened to `~`), skill publishers' names, license evidence, and the host id.
- **Personal data:** if you use real computer names as host ids, the reports can be linked to people. Treat them like other device inventory data, and involve your data-protection officer where that's required.

Full details are in the [privacy statement](privacy.md).

## What it doesn't do yet

Being explicit, so there are no surprises in a rollout:

- **No purchase records yet.** skillbom can tell that a skill needs a commercial license, but it can't check whether you bought one, or count seats against a purchase. Those entitlement rules are specified but not active.
- **Detection is heuristic.** On a held-out sample of public skills it matched hand labels on every unambiguous case, but it reads only license files, manifests and SKILL.md, not READMEs or source-file headers. The [accuracy section](research/corpus-2026-10.md#accuracy) has the details.
- **Two runtimes for now:** Claude Code and Codex skill locations, plus any folder you point it at.
- **Not legal advice.** License categories summarize license texts. For decisions with real consequences, legal should read the license itself, which the report links to.

## Questions

[Open an issue](https://github.com/eukgoekoko/skillbom/issues) on GitHub for anything about rolling skillbom out. Feedback from real rollouts is especially welcome.
