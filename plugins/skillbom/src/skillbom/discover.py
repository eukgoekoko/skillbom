"""Find installed skills and plugins on a host."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

PLUGIN_MANIFEST = Path(".claude-plugin/plugin.json")
MARKETPLACE_MANIFEST = Path(".claude-plugin/marketplace.json")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


@dataclass
class Candidate:
    kind: str  # "plugin" | "skill"
    path: Path
    platform: str
    install_scope: str  # managed | user | project | plugin | local | catalog
    boundary: Path  # highest directory whose LICENSE may apply (inclusive)
    source: dict = field(default_factory=lambda: {"type": "local"})
    parent: Candidate | None = None
    manifest: dict = field(default_factory=dict)  # plugin.json
    frontmatter: dict = field(default_factory=dict)  # SKILL.md
    marketplace_entry: dict = field(default_factory=dict)
    enabled: bool | None = None

    @property
    def name(self) -> str:
        return str(self.manifest.get("name") or self.frontmatter.get("name") or self.path.name)

    @property
    def version(self) -> str | None:
        v = self.manifest.get("version") or self.frontmatter.get("version")
        if not v and isinstance(self.frontmatter.get("metadata"), dict):
            v = self.frontmatter["metadata"].get("version")
        return str(v) if v else None

    @property
    def publisher(self) -> str | None:
        for author in (self.manifest.get("author"), self.marketplace_entry.get("author")):
            if isinstance(author, dict) and author.get("name"):
                return author["name"]
            if isinstance(author, str):
                return author
        return None


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_frontmatter(skill_md: Path) -> dict:
    try:
        text = skill_md.read_text(errors="replace")
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        # Unquoted colons etc. are common; fall back to plain key: value lines.
        return dict(re.findall(r"^([A-Za-z_-]+):\s*(.+)$", m.group(1), re.M))


def _skill(path: Path, **kw) -> Candidate:
    return Candidate(kind="skill", path=path, frontmatter=read_frontmatter(path / "SKILL.md"), **kw)


def _plugin_with_skills(path: Path, **kw) -> list[Candidate]:
    plugin = Candidate(kind="plugin", path=path, manifest=read_json(path / PLUGIN_MANIFEST), **kw)
    out = [plugin]
    for skill_md in sorted(path.glob("skills/*/SKILL.md")):
        out.append(_skill(skill_md.parent, platform=plugin.platform, install_scope="plugin",
                          boundary=plugin.boundary, source=plugin.source, parent=plugin))
    return out


def _skills_in(directory: Path, **kw) -> list[Candidate]:
    return [_skill(p.parent, **kw) for p in sorted(directory.glob("*/SKILL.md"))]


def scan_tree(root: Path, platform: str, install_scope: str) -> list[Candidate]:
    """Generic recursive scan: every plugin (with its skills) and standalone skill under root."""
    out: list[Candidate] = []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        if (d / PLUGIN_MANIFEST).is_file():
            out += _plugin_with_skills(d, platform=platform, install_scope=install_scope, boundary=root)
            dirnames.clear()
        elif "SKILL.md" in filenames:
            out.append(_skill(d, platform=platform, install_scope=install_scope, boundary=root))
            dirnames.clear()
        else:
            dirnames[:] = sorted(n for n in dirnames if n not in SKIP_DIRS)
    return out


def _marketplaces(plugins_dir: Path) -> dict[str, tuple[Path, dict]]:
    """Known marketplaces: name -> (clone location, marketplace.json)."""
    out = {}
    for name, info in read_json(plugins_dir / "known_marketplaces.json").items():
        loc = Path(info.get("installLocation") or plugins_dir / "marketplaces" / name)
        out[name] = (loc, read_json(loc / MARKETPLACE_MANIFEST))
    return out


def _entry_source(marketplace: str, entry: dict) -> dict:
    src = entry.get("source")
    out = {"type": "marketplace", "marketplace": marketplace}
    if isinstance(src, dict):
        url = src.get("url") or (f"https://github.com/{src['repo']}" if src.get("repo") else None)
        if url:
            out["url"] = url
        if src.get("sha") or src.get("ref"):
            out["ref"] = src.get("sha") or src.get("ref")
    return out


def _installed_plugins(plugins_dir: Path) -> list[Candidate]:
    # Deliberately doesn't read settings.json (to tell enabled from disabled plugins):
    # that file can hold credentials, and the scanner reads nothing it doesn't need.
    marketplaces = _marketplaces(plugins_dir)
    records = read_json(plugins_dir / "installed_plugins.json").get("plugins") or {}
    out: list[Candidate] = []
    for key, recs in records.items():
        name, _, mkt = key.partition("@")
        for rec in recs if isinstance(recs, list) else [recs]:
            path = Path(rec.get("installPath", ""))
            if not rec.get("installPath") or not path.is_dir():
                continue
            entry = next((p for p in marketplaces.get(mkt, (None, {}))[1].get("plugins", [])
                          if p.get("name") == name), {})
            scope = rec.get("scope", "user")
            cands = _plugin_with_skills(
                path, platform="claude-code",
                install_scope=scope if scope in ("managed", "user", "project", "local") else "user",
                boundary=path, source=_entry_source(mkt, entry))
            cands[0].marketplace_entry = entry
            out += cands
    if not records:
        # No install registry: fall back to whatever is in the plugin cache.
        cache = plugins_dir / "cache"
        if cache.is_dir():
            out += scan_tree(cache, "claude-code", "user")
    return out


def _catalogs(plugins_dir: Path) -> list[Candidate]:
    """Plugins that marketplace clones make available on disk (not necessarily installed)."""
    out: list[Candidate] = []
    for mkt, (loc, manifest) in _marketplaces(plugins_dir).items():
        for entry in manifest.get("plugins", []):
            src = entry.get("source")
            if not isinstance(src, str):
                continue  # remote source, not on disk until installed
            path = (loc / src).resolve()
            if not path.is_dir():
                continue
            cands = _plugin_with_skills(path, platform="claude-code", install_scope="catalog",
                                        boundary=loc, source=_entry_source(mkt, entry))
            if not cands[0].manifest:
                cands[0].manifest = {k: entry[k] for k in ("name", "version", "author") if k in entry}
            cands[0].marketplace_entry = entry
            out += cands
    return out


def _read_lock(path: Path) -> dict[str, dict]:
    """Entries of an `npx skills` lock file, keyed by installed folder name."""
    entries = read_json(path).get("skills")
    if not isinstance(entries, dict):
        return {}
    # Folder names are the installer's sanitizeName() of the lock key.
    return {re.sub(r"[^a-z0-9._]+", "-", k.lower()).strip("-."): v
            for k, v in entries.items() if isinstance(v, dict)}


def project_lock(directory: Path) -> dict[str, dict]:
    """`skills-lock.json` (version 1), written into the directory `npx skills` ran in;
    its skills are copied to <directory>/.agents/skills."""
    return _read_lock(directory / "skills-lock.json")


def skills_lock(home: Path) -> dict[str, dict]:
    """Install records of `npx skills` (vercel-labs/skills) for the home directory:
    folder name -> lock entry.

    The installer copies only the skill's own folder, so a LICENSE at the root of its
    repository is never on disk; the recorded source is the only lead to it. Global
    installs are recorded in .skill-lock.json; an install run *from* the home directory
    counts as a project install and is recorded in ~/skills-lock.json.
    """
    state = os.environ.get("XDG_STATE_HOME")
    path = Path(state) / "skills/.skill-lock.json" if state else home / ".agents/.skill-lock.json"
    return {**project_lock(home), **_read_lock(path)}


def _public_url(url: str) -> str:
    """Drop credentials and query strings: a private repo's URL can carry an access token
    (https://user:TOKEN@host/...), and BOMs are meant to be shared."""
    if url.startswith("git@"):
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname + (f":{parts.port}" if parts.port else ""), parts.path, "", ""))


def _lock_source(entry: dict) -> dict | None:
    url = entry.get("sourceUrl")
    if not url and entry.get("sourceType") == "github" and entry.get("source"):
        url = f"https://github.com/{entry['source']}"
    if not isinstance(url, str) or not url.startswith(("https://", "http://", "git@")):
        return None  # local or unrecognized source: nothing to point at
    url = _public_url(url)
    out = {"type": "git", "url": url[:-4] if url.endswith(".git") else url}
    folder = str(Path(str(entry.get("skillPath") or "")).parent)
    if folder not in ("", "."):
        out["path"] = folder
    return out


def _apply_lock(cands: list[Candidate], lock: dict[str, dict]) -> list[Candidate]:
    for c in cands:
        if c.source.get("type") == "local" and c.path.name in lock:
            c.source = _lock_source(lock[c.path.name]) or c.source
    return cands


def agents(home: Path) -> list[Candidate]:
    """~/.agents/skills: the shared directory `npx skills` installs into. Claude Code gets a
    symlink to it in ~/.claude/skills; agents that read it directly (Codex, Cursor, Amp, ...)
    get nothing else, so skills installed only for them live here alone."""
    skills = home / ".agents/skills"
    if not skills.is_dir():
        return []
    return _apply_lock(_skills_in(skills, platform="agents", install_scope="user", boundary=skills),
                       skills_lock(home))


def claude_code(home: Path, include_catalogs: bool = False) -> list[Candidate]:
    base = home / ".claude"
    out: list[Candidate] = []
    skills = base / "skills"
    if skills.is_dir():
        out += _apply_lock([c for c in _skills_in(skills, platform="claude-code", install_scope="user",
                                                   boundary=skills) if c.path.name != "synced"],
                           skills_lock(home))
        # Skills synced from the user's claude.ai account: synced/<org>_<account>/<skill>/
        for skill_md in sorted(skills.glob("synced/*/*/SKILL.md")):
            out.append(_skill(skill_md.parent, platform="claude-code", install_scope="user",
                              boundary=skill_md.parent,
                              source={"type": "registry", "url": "https://claude.ai"}))
    plugins = base / "plugins"
    if plugins.is_dir():
        out += _installed_plugins(plugins)
        if include_catalogs:
            out += _catalogs(plugins)
    return out


def codex(home: Path) -> list[Candidate]:
    skills = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "skills"
    if not skills.is_dir():
        return []
    return _apply_lock(_skills_in(skills, platform="codex-cli", install_scope="user", boundary=skills),
                       skills_lock(home))


def managed() -> list[Candidate]:
    roots = {"darwin": ["/Library/Application Support/ClaudeCode"],
             "linux": ["/etc/claude-code"]}.get(sys.platform, [])
    out: list[Candidate] = []
    for r in map(Path, roots):
        if r.is_dir():
            out += scan_tree(r, "claude-code", "managed")
    return out


def project(directory: Path) -> list[Candidate]:
    out: list[Candidate] = []
    lock = project_lock(directory)
    for sub, platform in ((".claude/skills", "claude-code"), (".codex/skills", "codex-cli"),
                          (".agents/skills", "agents")):
        d = directory / sub
        if d.is_dir():
            out += _apply_lock(_skills_in(d, platform=platform, install_scope="project", boundary=directory), lock)
    return out
