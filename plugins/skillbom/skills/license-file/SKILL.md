---
name: license-file
description: Create or update a skill-license.yaml for a skill or plugin the user is authoring, so its license travels with the folder in machine-readable form. Use when the user wants to add a license (file) to their skill or plugin, declare its license, publish a skill, or runs /skillbom:license-file. Also use to refresh the content hash after editing a skill that already has one.
---

# Skill license file

Write a `skill-license.yaml` ([specification](https://eukgoekoko.github.io/skillbom/license-file.html)) next to the skill's `SKILL.md`, or next to a plugin's `.claude-plugin/plugin.json`.

The launcher is `bin/skillbom`, two directories above this skill's base directory: `<base>/../../bin/skillbom`. Use its absolute path.

## Steps

1. **Find the folder.** It's the skill or plugin the user is working on: usually a folder with a `SKILL.md` in the current project. If several exist and it's unclear which one, ask.
2. **Preview** without writing anything:

   ```sh
   "<base>/../../bin/skillbom" init "<folder>" --dry-run
   ```

   `init` fills in the id (`publisher/name`), version and license from the frontmatter, manifests, LICENSE files and the git remote. Its notes (on stderr) say where each value came from.
3. **Confirm with the user** before writing: the publisher, the license and the version. Adjust with `--publisher`, `--name` or `--id`, `--license "<SPDX expression>"` and `--version`. Never pick a license for the user: if none is detected, ask which one they want.
4. **Write it**: the same command without `--dry-run`. If the notes say the license text lives outside the folder, offer `--copy-license`, which copies it in so the text travels with the skill.
5. **Afterwards:** remind the user to commit the file, and to run `init --update` after changing the skill, which refreshes the content hash (add `--version` to bump the version).

If the file already exists, use `--update`. For commercial terms (`LicenseRef-…` offers with seats, prices and grants), `init` stops on purpose: point the user to the [offers section of the specification](https://eukgoekoko.github.io/skillbom/license-file.html#offers) and help them write those by hand.
