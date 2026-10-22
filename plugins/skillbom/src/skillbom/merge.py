"""Merge Skill BOMs from several hosts into one organization-wide BOM."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from skillbom import __version__
from skillbom.bom import number_findings, summarize

STATUS_RANK = {"declared": 2, "inferred": 1, "unknown": 0}
# Findings derived from license detection; they follow the BOM whose detection was kept.
LICENSE_RULES = {"license-unknown", "license-invalid", "license-denied", "license-conflict",
                 "license-review", "commercial-use-restricted"}


def _strength(component: dict) -> tuple[int, float]:
    lic = component["license"]
    conf = max((e.get("confidence", 0) for e in lic.get("evidence", [])
                if e.get("expression") == lic["expression"]), default=0)
    return STATUS_RANK.get(lic["status"], 0), conf


def policies(boms: list[dict]) -> list[dict]:
    """Distinct policies the input BOMs were evaluated against."""
    out: list[dict] = []
    for b in boms:
        p = b["metadata"].get("policy")
        if p not in out:
            out.append(p)
    return out


def merge(boms: list[dict], organization: str | None = None) -> dict:
    if not boms:
        raise ValueError("nothing to merge")
    comps: dict[str, dict] = {}
    license_from: dict[str, int] = {}  # bomRef -> index of the BOM whose license detection is kept
    for i, b in enumerate(boms):
        for c in b["components"]:
            ref = c["bomRef"]
            if ref not in comps:
                comps[ref] = copy.deepcopy(c)
                license_from[ref] = i
                continue
            m = comps[ref]
            seen = {(x["host"], x["path"]) for x in m["installations"]}
            m["installations"] += [copy.deepcopy(x) for x in c["installations"] if (x["host"], x["path"]) not in seen]
            if _strength(c) > _strength(m):
                for key in ("license", "entitlement"):
                    m[key] = copy.deepcopy(c[key])
                license_from[ref] = i

    findings, seen_f = [], set()
    for i, b in enumerate(boms):
        for f in b.get("findings", []):
            if f["rule"] in LICENSE_RULES and any(license_from.get(r) != i for r in f["components"]):
                continue
            key = (f["rule"], tuple(f["components"]), f["message"])
            if key not in seen_f:
                seen_f.add(key)
                findings.append(copy.deepcopy(f))

    hosts: dict[str, dict] = {}
    for b in boms:
        for h in b["metadata"]["scope"]["hosts"]:
            if h["id"] not in hosts:
                hosts[h["id"]] = copy.deepcopy(h)
                continue
            m = hosts[h["id"]]
            for key in ("platforms", "roots"):
                if h.get(key):
                    m[key] = sorted(set(m.get(key, [])) | set(h[key]))

    edges: dict[tuple[str, str], set[str]] = {}
    for b in boms:
        for d in b.get("dependencies", []):
            edges.setdefault((d["ref"], d.get("relation", "contains")), set()).update(d["dependsOn"])

    orgs = {b["metadata"]["scope"].get("organization") for b in boms} - {None}
    org = organization or (orgs.pop() if len(orgs) == 1 else None)
    metadata = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tool": {"name": "skillbom", "version": __version__},
        "scope": {**({"organization": org} if org else {}), "hosts": sorted(hosts.values(), key=lambda h: h["id"])},
        "mergedFrom": [b["serialNumber"] for b in boms],
    }
    ps = policies(boms)
    if len(ps) == 1 and ps[0]:
        metadata["policy"] = ps[0]

    components = list(comps.values())
    findings = number_findings(findings)
    return {
        "bomFormat": "SkillBOM",
        "specVersion": "0.1",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "metadata": metadata,
        "components": components,
        "dependencies": [{"ref": r, "dependsOn": sorted(deps), "relation": rel}
                         for (r, rel), deps in sorted(edges.items())],
        "findings": findings,
        "summary": summarize(components, findings),
    }
