"""Assemble a Skill BOM document from discovered candidates."""

from __future__ import annotations

import getpass
import hashlib
import platform as _platform
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from skillbom import __version__
from skillbom.discover import Candidate
from skillbom.hashing import content_hash
from skillbom.licenses import detect
from skillbom.rules import Policy, entitlement_status, evaluate

SEVERITIES = ["critical", "high", "medium", "low", "info"]


def host_id() -> str:
    """Pseudonymous, stable per machine and OS user."""
    raw = f"{_platform.node()}:{getpass.getuser()}".encode()
    return "h-" + hashlib.sha256(raw).hexdigest()[:8]


def build(candidates: list[Candidate], *, roots: list[Path], policy: Policy | None = None,
          home: Path | None = None, host: str | None = None, organization: str | None = None) -> dict:
    policy = policy or Policy()
    host = host or host_id()
    home_str = str(home or Path.home())

    def display(p: Path) -> str:
        s = str(p)
        return "~" + s[len(home_str):] if s == home_str or s.startswith(home_str + "/") else s

    components: dict[str, dict] = {}
    ref_of: dict[int, str] = {}  # id(candidate) -> bomRef
    edges: set[tuple[str, str]] = set()
    findings: list[dict] = []

    for c in candidates:
        digest = content_hash(c.path)
        ref = f"{c.kind}-{digest[:12]}"
        ref_of[id(c)] = ref
        install = {"host": host, "platform": c.platform, "path": display(c.path), "installScope": c.install_scope}
        if c.enabled is not None:
            install["enabled"] = c.enabled
        if c.parent is not None and id(c.parent) in ref_of:
            edges.add((ref_of[id(c.parent)], ref))
        if ref in components:
            components[ref]["installations"].append(install)
            continue

        d = detect(c)
        declared_hash = ((d.declared.get("subject") or {}).get("contentHash") or {})
        if declared_hash.get("alg") == "sha256" and declared_hash.get("value"):
            integrity = "match" if declared_hash["value"] == digest else "modified"
        else:
            integrity = "unverified"

        comp = {"bomRef": ref, "kind": c.kind}
        subject_id = (d.declared.get("subject") or {}).get("id")
        if subject_id:
            comp["id"] = subject_id
        comp["name"] = c.name
        if c.version:
            comp["version"] = c.version
        if c.publisher:
            comp["publisher"] = c.publisher
        comp["source"] = c.source
        comp["contentHash"] = {"alg": "sha256", "value": digest}
        comp["integrity"] = integrity
        comp["license"] = {"status": d.status, "expression": d.expression}
        if d.evidence:
            comp["license"]["evidence"] = [e.to_json(display) for e in d.evidence]
        comp["entitlement"] = {"status": entitlement_status(d.expression)}
        comp["installations"] = [install]
        components[ref] = comp
        findings += evaluate(ref, c.name, d, integrity, policy)

    findings = number_findings(findings)
    comps = list(components.values())
    platforms = sorted({c.platform for c in candidates})
    scope_host = {"id": host, "os": _platform.system().lower()}
    if platforms:
        scope_host["platforms"] = platforms
    scope_host["roots"] = [display(r) for r in roots]

    metadata = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tool": {"name": "skillbom", "version": __version__},
        "scope": {**({"organization": organization} if organization else {}), "hosts": [scope_host]},
    }
    if (p := policy.to_json()) is not None:
        metadata["policy"] = p

    deps: dict[str, list[str]] = {}
    for parent, child in sorted(edges):
        deps.setdefault(parent, []).append(child)

    return {
        "bomFormat": "SkillBOM",
        "specVersion": "0.1",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "metadata": metadata,
        "components": comps,
        "dependencies": [{"ref": p, "dependsOn": cs, "relation": "contains"} for p, cs in deps.items()],
        "findings": findings,
        "summary": summarize(comps, findings),
    }


def number_findings(findings: list[dict]) -> list[dict]:
    """Sort findings by severity and give them sequential ids (F1, F2, ...)."""
    ordered = sorted(findings, key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"], f["components"]))
    return [{"id": f"F{i}", **{k: v for k, v in f.items() if k != "id"}} for i, f in enumerate(ordered, 1)]


def summarize(comps: list[dict], findings: list[dict]) -> dict:
    status = Counter(c["license"]["status"] for c in comps)
    severity = Counter(f["severity"] for f in findings)
    return {
        "components": len(comps),
        "installations": sum(len(c["installations"]) for c in comps),
        "hosts": len({i["host"] for c in comps for i in c["installations"]}),
        "byKind": dict(Counter(c["kind"] for c in comps)),
        "byLicense": dict(Counter(c["license"]["expression"] for c in comps).most_common()),
        "byLicenseStatus": {s: status.get(s, 0) for s in ("declared", "inferred", "unknown")},
        "byEntitlement": dict(Counter(c["entitlement"]["status"] for c in comps)),
        "findingsBySeverity": {s: severity.get(s, 0) for s in SEVERITIES},
    }
