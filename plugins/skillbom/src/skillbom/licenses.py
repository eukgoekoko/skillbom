"""Collect license evidence for a candidate and resolve it to one expression."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from skillbom import spdx, textmatch
from skillbom.discover import Candidate, read_json

# Tie-break order when confidences are equal (docs/skill-bom.md).
SOURCE_ORDER = ["skill-license-file", "plugin-manifest", "skill-frontmatter",
                "text-match", "repo-license-file", "marketplace-metadata"]
INHERITED_SOURCES = {"repo-license-file", "marketplace-metadata"}
LICENSE_FILE = re.compile(r"^(un)?licen[cs]e|^copying", re.I)
_FILE_REF = re.compile(r"[\w./-]*(?:LICEN[CS]E|COPYING)[\w.-]*", re.I)
REPO_FACTOR = 0.8  # a repository-level LICENSE may not be meant for every skill in it


@dataclass
class Evidence:
    source: str
    path: Path
    expression: str | None = None
    confidence: float | None = None
    value: str | None = None  # raw declared text when it isn't a valid SPDX expression

    def to_json(self, display) -> dict:
        out = {"source": self.source, "path": display(self.path)}
        if self.expression:
            out["expression"] = self.expression
        if self.confidence is not None:
            out["confidence"] = round(self.confidence, 2)
        if self.value:
            out["value"] = self.value
        return out


@dataclass
class Detection:
    evidence: list[Evidence] = field(default_factory=list)
    declared: dict = field(default_factory=dict)  # parsed skill-license file, if any
    declared_error: str | None = None

    @property
    def best(self) -> Evidence | None:
        """Highest-confidence evidence from the component itself; repository and
        marketplace evidence only count when the component says nothing."""
        resolved = [e for e in self.evidence if e.expression]
        own = [e for e in resolved if e.source not in INHERITED_SOURCES]
        pool = own or resolved
        if not pool:
            return None
        return max(pool, key=lambda e: (e.confidence or 0, -SOURCE_ORDER.index(e.source)))

    @property
    def status(self) -> str:
        best = self.best
        if best is None:
            return "unknown"
        return "declared" if best.source == "skill-license-file" else "inferred"

    @property
    def expression(self) -> str:
        best = self.best
        return best.expression if best else spdx.NOASSERTION


def license_files(directory: Path) -> list[Path]:
    try:
        return sorted(p for p in directory.iterdir() if p.is_file() and LICENSE_FILE.match(p.name))
    except OSError:
        return []


def _text_evidence(files: list[Path], source: str, factor: float = 1.0) -> Evidence | None:
    """One evidence for the license files of a directory (several = dual licensing)."""
    if not files:
        return None
    ids, confs = [], []
    for f in files:
        try:
            hit = textmatch.identify(f.read_text(errors="replace"))
        except OSError:
            hit = None
        if hit and hit[0] not in ids:
            ids.append(hit[0])
            confs.append(hit[1])
    if not ids:
        # A license text we can't identify is still a license: flag it for review.
        return Evidence(source, files[0], spdx.CUSTOM, 0.3 * factor)
    return Evidence(source, files[0], " OR ".join(ids), min(confs) * factor)


def _interpret(value, source: str, path: Path, base: Path) -> list[Evidence]:
    """Evidence from a declared `license` value (manifest field, frontmatter key)."""
    if isinstance(value, dict):  # old npm style {"type": "MIT"}
        value = value.get("type", "")
    text = str(value).strip()
    if not text:
        return []
    expr = spdx.normalize(text)
    if expr:
        return [Evidence(source, path, expr, 0.9)]
    if named := spdx.from_name(text):
        out = [Evidence(source, path, named, 0.8, value=text)]
        if named != spdx.PROPRIETARY:
            return out
        return out + _referenced(text, base)
    proprietary = re.search(r"\bproprietary\b", text, re.I)
    out = [Evidence(source, path, spdx.PROPRIETARY if proprietary else None,
                    0.6 if proprietary else None, value=text)]
    return out + _referenced(text, base)


def _referenced(text: str, base: Path) -> list[Evidence]:
    """Evidence from the first license file a declared value names, if it exists."""
    for ref in _FILE_REF.findall(text):
        target = base / ref
        if target.is_file():
            ev = _text_evidence([target], "text-match")
            return [ev] if ev else []
    return []


def _license_file(directory: Path) -> tuple[Path | None, dict, str | None]:
    for name in ("skill-license.yaml", "skill-license.yml", "skill-license.json"):
        p = directory / name
        if p.is_file():
            try:
                text = p.read_text()
                data = json.loads(text) if p.suffix == ".json" else yaml.safe_load(text)
                return p, data if isinstance(data, dict) else {}, None
            except (OSError, ValueError, yaml.YAMLError) as e:
                return p, {}, f"unreadable: {e}"
    return None, {}, None


def detect(c: Candidate) -> Detection:
    d = Detection()
    ev = d.evidence

    lf, data, err = _license_file(c.path)
    if lf:
        d.declared, d.declared_error = data, err
        raw = str((data.get("license") or {}).get("expression", ""))
        expr = spdx.normalize(raw) if raw else None
        if expr:
            ev.append(Evidence("skill-license-file", lf, expr, 1.0))
        else:
            d.declared_error = d.declared_error or f"invalid SPDX expression: {raw!r}"
            ev.append(Evidence("skill-license-file", lf, value=raw or None))

    if c.kind == "plugin" and "license" in c.manifest:
        ev += _interpret(c.manifest["license"], "plugin-manifest", c.path / ".claude-plugin/plugin.json", c.path)
    pkg = c.path / "package.json"
    if pkg.is_file() and "license" in (pkg_data := read_json(pkg)):
        ev += _interpret(pkg_data["license"], "plugin-manifest", pkg, c.path)

    if "license" in c.frontmatter:
        ev += _interpret(c.frontmatter["license"], "skill-frontmatter", c.path / "SKILL.md", c.path)

    seen = {e.path for e in ev if e.source == "text-match"}
    own = [f for f in license_files(c.path) if f not in seen]
    if own and (t := _text_evidence(own, "text-match")):
        ev.append(t)

    # Nearest ancestor (up to the boundary) that has license files.
    directory = c.path
    while directory != c.boundary and c.boundary in directory.parents:
        directory = directory.parent
        files = license_files(directory)
        if files:
            if t := _text_evidence(files, "repo-license-file", REPO_FACTOR):
                ev.append(t)
            break

    if "license" in c.marketplace_entry:
        manifest = c.boundary / ".claude-plugin/marketplace.json"
        for e in _interpret(c.marketplace_entry["license"], "marketplace-metadata", manifest, c.boundary):
            if e.confidence:
                e.confidence = min(e.confidence, 0.7)
            ev.append(e)
    return d
