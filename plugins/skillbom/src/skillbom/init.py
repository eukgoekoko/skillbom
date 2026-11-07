"""Write or update a skill license file (docs/license-file.md) for a skill or plugin."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from skillbom import spdx
from skillbom.discover import PLUGIN_MANIFEST, Candidate, read_frontmatter, read_json
from skillbom.hashing import content_hash
from skillbom.licenses import detect, license_files

FILE_NAMES = ("skill-license.yaml", "skill-license.yml", "skill-license.json")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
HEADER = "# Skill license file, specVersion 0.1: https://eukgoekoko.github.io/skillbom/license-file.html\n"


class InitError(Exception):
    """A problem the user has to resolve, e.g. with an option."""


def _slug(text: str, allowed: str) -> str:
    return re.sub(rf"[^{allowed}]+", "-", text.lower()).strip("-._")


def _git(directory: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=directory, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _remote_owner(directory: Path) -> str | None:
    url = _git(directory, "config", "--get", "remote.origin.url") or ""
    m = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?/?$", url)
    return m.group(1) if m else None


def _candidate(directory: Path) -> Candidate:
    top = _git(directory, "rev-parse", "--show-toplevel")
    boundary = Path(top).resolve() if top and Path(top).resolve() in [directory, *directory.parents] else directory
    common = dict(path=directory, platform="claude-code", install_scope="local", boundary=boundary)
    if (directory / PLUGIN_MANIFEST).is_file():
        return Candidate(kind="plugin", manifest=read_json(directory / PLUGIN_MANIFEST), **common)
    if (directory / "SKILL.md").is_file():
        return Candidate(kind="skill", frontmatter=read_frontmatter(directory / "SKILL.md"), **common)
    raise InitError(f"{directory} has no SKILL.md or .claude-plugin/plugin.json")


def _existing(directory: Path) -> Path | None:
    return next((directory / n for n in FILE_NAMES if (directory / n).is_file()), None)


def _expression(value: str) -> str:
    expr = spdx.normalize(value)
    if expr is None:
        raise InitError(f"--license {value!r} is not a valid SPDX expression (e.g. MIT, Apache-2.0, MIT OR Apache-2.0)")
    if "LicenseRef-" in expr:
        raise InitError("commercial LicenseRef- terms need offers, which init doesn't write; "
                        "add them by hand as described at https://eukgoekoko.github.io/skillbom/license-file.html#offers")
    return expr


def init(directory: Path, *, publisher: str | None = None, name: str | None = None, id: str | None = None,
         version: str | None = None, license: str | None = None, license_text: str | None = None,
         copy_license: bool = False, update: bool = False, dry_run: bool = False) -> tuple[Path, str, list[str]]:
    """Build the skill license file for `directory`.

    Returns (path, file text, notes). Writing is left to the caller, except --copy-license,
    which copies the inherited license text into the directory first so the hash covers it
    (not with dry_run, where the hash then excludes the copy).
    """
    directory = directory.resolve()
    c = _candidate(directory)
    notes: list[str] = []
    existing = _existing(directory)
    if existing and not update:
        raise InitError(f"{existing.name} already exists; use --update to refresh its content hash and version")
    if update and not existing:
        raise InitError("there is no skill license file to update; run without --update to create one")
    if version and not SEMVER_RE.match(version):
        raise InitError(f"--version {version!r} is not a semantic version such as 1.2.0")

    if update:
        doc = yaml.safe_load(existing.read_text()) or {}
        if version:
            doc.setdefault("subject", {})["version"] = version
        if license:
            doc.setdefault("license", {})["expression"] = _expression(license)
        if license_text:
            doc.setdefault("license", {})["text"] = license_text
    else:
        # Identity
        if id:
            if not ID_RE.match(id):
                raise InitError(f"--id {id!r} must look like publisher/name (lowercase letters, digits, - . _)")
            subject_id = id
        else:
            author = c.publisher
            pub = publisher or author or _remote_owner(directory)
            if not pub:
                raise InitError("can't tell the publisher; pass --publisher (e.g. your GitHub user or organization)")
            subject_id = f"{_slug(pub, 'a-z0-9-')}/{_slug(name or c.name, 'a-z0-9._-')}"
        ver = version or c.version or "0.1.0"
        if not SEMVER_RE.match(ver):
            notes.append(f"version {ver!r} isn't a semantic version; using 0.1.0 (set --version)")
            ver = "0.1.0"
        elif not (version or c.version):
            notes.append("no version found; using 0.1.0 (set --version)")

        # License: explicit, or what the scanner can tell from the skill and its surroundings.
        detection = detect(c)
        if license:
            expr = _expression(license)
        else:
            expr = detection.expression
            if expr == spdx.NOASSERTION:
                raise InitError("no license found; pass --license with an SPDX expression")
            if "LicenseRef-" in expr:
                raise InitError(f"the detected license ({expr}) isn't a standard one; pass --license explicitly")
            best = detection.best
            notes.append(f"license {expr} taken from {best.source} ({best.path.name})")

        # License text: explicit, the skill's own license file, or the inherited one.
        text = license_text
        if not text:
            own = license_files(directory)
            if own:
                text = own[0].name
            else:
                inherited = next((e.path for e in detection.evidence
                                  if e.source == "repo-license-file" and e.expression), None)
                if inherited and copy_license:
                    target = directory / ("LICENSE" if not (directory / "LICENSE").exists() else inherited.name)
                    text = target.name
                    if dry_run:
                        notes.append(f"would copy {os.path.relpath(inherited, directory)} to {target.name} "
                                     "(the content hash shown excludes it)")
                    else:
                        shutil.copyfile(inherited, target)
                        notes.append(f"copied {os.path.relpath(inherited, directory)} to {target.name}, "
                                     "so the text travels with the skill")
                elif inherited:
                    text = os.path.relpath(inherited, directory)
                    notes.append(f"the license text is outside this folder ({text}); "
                                 "use --copy-license so it travels with the skill")

        subject = {"kind": c.kind, "id": subject_id, "version": ver}
        if c.name and c.name != subject_id.split("/", 1)[1]:
            subject["name"] = c.name
        doc = {"specVersion": "0.1", "subject": subject, "license": {"expression": expr}}
        if text:
            doc["license"]["text"] = text
        fm = c.frontmatter.get("license") if c.kind == "skill" else c.manifest.get("license")
        if fm and spdx.normalize(str(fm)) != expr:
            notes.append(f"the declared license ({fm!r}) differs from {expr}; keep them consistent")

    doc.setdefault("subject", {})["contentHash"] = {"alg": "sha256", "value": content_hash(directory)}
    path = existing or directory / "skill-license.yaml"
    if path.suffix == ".json":
        return path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n", notes
    return path, HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), notes
