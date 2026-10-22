# skillbom — Claude Code plugin

See what licenses your installed AI agent skills and plugins are under.

```
/plugin marketplace add eukgoekoko/skillbom
/plugin install skillbom@skillbom
/skillbom:audit
```

Or just ask Claude *"what licenses are my skills under?"*. The `audit` skill:

1. **Scans** the skills and plugins installed for Claude Code and Codex: user, project, managed and claude.ai-synced skills, plus installed plugins and the skills inside them.
2. **Works out** each one's license from license files, manifests, SKILL.md and LICENSE texts.
3. **Writes** a Skill BOM (a JSON inventory of every skill and plugin, its source and its license) and an HTML audit report to `~/skillbom-reports/<timestamp>/`.

**Privacy:** everything runs on your machine. The plugin makes no network requests, except that on first use it may download PyYAML from PyPI (via `uv`, or `pip` into `~/.cache/skillbom`) if no Python with PyYAML is available. See the [privacy statement](https://eukgoekoko.github.io/skillbom/privacy.html).

**Requirements:** Python 3.9 or newer.

**Help and source:** [github.com/eukgoekoko/skillbom](https://github.com/eukgoekoko/skillbom). Report issues [on GitHub](https://github.com/eukgoekoko/skillbom/issues). Licensed under Apache-2.0.
