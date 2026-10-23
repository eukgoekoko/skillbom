# Privacy statement

skillbom (the command-line tool and the Claude Code plugin) runs entirely on your machine.

- **No data leaves your machine.** The scanner reads skill and plugin files under the directories it scans and writes its reports to local files: by default `~/skillbom-reports/` when run through the plugin, otherwise wherever you point it. It sends no telemetry, analytics or reports anywhere.
- **No network access.** The Claude Code plugin downloads and installs nothing: the scanner and its one dependency (PyYAML) ship with it as readable source, and it makes no network requests. If you install the command-line tool with `pip`, that installation is an ordinary package download, subject to the package index's own privacy policy.
- **No credentials.** The scanner reads skill and plugin files and the plugin lists Claude Code keeps (`installed_plugins.json`, `known_marketplaces.json`). It deliberately doesn't read `settings.json` or other files that can hold credentials or tokens.
- **What reports contain.** A Skill BOM lists file paths, content hashes, license identifiers with the evidence behind them (including declared license values), and a host identifier. Paths under your home directory are written as `~`. The host identifier is a pseudonymous hash of the machine and user name unless you set `--host-id`. Reports are yours: share them only if you choose to.
- **Claude.** When you use the plugin inside Claude Code, Claude reads the scanner's summary to answer you, as with any tool output in your session; that is governed by your agreement with Anthropic.
- **This website** is a static page on GitHub Pages and sets no cookies of its own. GitHub's privacy statement applies to the hosting.

Questions: write to [hello@skillbom.org](mailto:hello@skillbom.org) or [open an issue](https://github.com/eukgoekoko/skillbom/issues).
