"""Policy and finding rules (catalog in docs/skill-bom.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

from skillbom import spdx
from skillbom.licenses import INHERITED_SOURCES, Detection

DEFAULT_SEVERITY = {
    "license-denied": "critical",
    "commercial-use-restricted": "high",
    "composition-incompatible": "high",
    "license-unknown": "medium",
    "license-invalid": "medium",
    "license-conflict": "medium",
    "license-review": "medium",
    "integrity-modified": "info",
}


@dataclass
class Policy:
    id: str | None = None
    version: str | None = None
    allowed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    severities: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Policy:
        data = yaml.safe_load(path.read_text()) or {}
        return cls(id=data.get("id"), version=str(data["version"]) if "version" in data else None,
                   allowed=data.get("allowedLicenses") or [], denied=data.get("deniedLicenses") or [],
                   severities=data.get("severities") or {})

    def permits(self, license_id: str) -> bool:
        if any(fnmatchcase(license_id, p) for p in self.denied):
            return False
        return not self.allowed or any(fnmatchcase(license_id, p) for p in self.allowed)

    def to_json(self) -> dict | None:
        if not (self.id or self.allowed or self.denied):
            return None
        out = {k: v for k, v in (("id", self.id), ("version", self.version)) if v}
        if self.allowed:
            out["allowedLicenses"] = self.allowed
        if self.denied:
            out["deniedLicenses"] = self.denied
        return out


def entitlement_status(expression: str) -> str:
    choices = spdx.choices(expression)
    if not choices:
        return "unknown"
    if any(spdx.choice_grants(c, "commercialUse") for c in choices):
        return "not-required"
    # Commercial-only or unmapped licenses need the purchase registry, which isn't connected yet.
    return "unknown"


def _composition_problems(declared: dict) -> list[str]:
    problems = []
    for inc in declared.get("includes") or []:
        relation = inc.get("relation")
        expr = spdx.normalize(str(inc.get("license", "")))
        if relation == "references" or not expr:
            continue
        needed = ["compose"] + (["modify"] if relation in ("modified", "derived") else [])
        verdicts = []
        for choice in spdx.choices(expr):
            checks = [spdx.choice_grants(choice, g) for g in needed]
            verdicts.append(None if None in checks else all(checks))
        if verdicts and not any(v is None or v for v in verdicts):
            problems.append(f"{inc.get('id')} ({expr}) does not permit being {relation} into a plugin")
    return problems


def evaluate(ref: str, name: str, detection: Detection, integrity: str, policy: Policy) -> list[dict]:
    """Findings (without ids) for one component."""
    found: list[tuple[str, str, str | None]] = []  # (rule, message, remediation)
    expr = detection.expression

    if detection.declared_error:
        found.append(("license-invalid", f"skill-license file of '{name}' is invalid: {detection.declared_error}",
                      "Fix the file so it validates against schema/skill-license.schema.json."))
    if detection.status == "unknown":
        found.append(("license-unknown", f"No license found for '{name}'.",
                      "Ask the author for a license, replace the component, or remove it."))
    else:
        choices = spdx.choices(expr)
        if choices and not any(all(policy.permits(lid) for lid in c) for c in choices):
            found.append(("license-denied", f"'{name}' is licensed {expr}, which the policy does not allow.",
                          "Remove the component or obtain it under an allowed license."))
        if choices and all(spdx.choice_grants(c, "commercialUse") is False for c in choices):
            found.append(("commercial-use-restricted",
                          f"'{name}' is licensed {expr}, which does not permit commercial use.",
                          "Obtain a commercial license from the author or stop using it for work."))
        if spdx.CUSTOM in expr:
            found.append(("license-review", f"'{name}' has a license text that isn't a known license.",
                          "Have someone read the license and record it as a LicenseRef- in a skill-license file."))
        own = {e.expression for e in detection.evidence
               if e.source not in INHERITED_SOURCES and e.expression and (e.confidence or 0) >= 0.5}
        if len(own) > 1:
            found.append(("license-conflict",
                          f"License evidence for '{name}' disagrees: {', '.join(sorted(own))}.",
                          "Check the license texts and declare one expression in a skill-license file."))
    if integrity == "modified":
        found.append(("integrity-modified",
                      f"Content of '{name}' differs from the hash declared in its skill-license file.", None))
    for problem in _composition_problems(detection.declared):
        found.append(("composition-incompatible", problem, "Remove the component or get a license that grants it."))

    out = []
    for rule, message, remediation in found:
        f = {"rule": rule, "severity": policy.severities.get(rule, DEFAULT_SEVERITY[rule]),
             "components": [ref], "message": message}
        if remediation:
            f["remediation"] = remediation
        out.append(f)
    return out
