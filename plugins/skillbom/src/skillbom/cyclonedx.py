"""Export a Skill BOM as CycloneDX 1.6 JSON (mapping in docs/skill-bom.md, "Mapping to CycloneDX")."""

from __future__ import annotations

from skillbom import __version__

SPEC_VERSION = "1.6"
HASH_ALGS = {"sha256": "SHA-256", "sha512": "SHA-512"}
NS = "skillbom"


def _prop(name: str, value) -> dict:
    return {"name": f"{NS}:{name}", "value": str(value).lower() if isinstance(value, bool) else str(value)}


def _tool() -> dict:
    return {"type": "application", "name": "skillbom", "version": __version__,
            "externalReferences": [{"type": "website", "url": "https://eukgoekoko.github.io/skillbom/"}]}


def _component(c: dict) -> dict:
    out = {"type": "application", "bom-ref": c["bomRef"], "name": c["name"]}
    for key in ("version", "publisher"):
        if c.get(key):
            out[key] = c[key]
    if c.get("id"):
        out["group"], _, _ = c["id"].partition("/")
    out["hashes"] = [{"alg": HASH_ALGS[c["contentHash"]["alg"]], "content": c["contentHash"]["value"]}]

    lic = c["license"]
    if lic["expression"] != "NOASSERTION":
        out["licenses"] = [{"expression": lic["expression"]}]

    src = c["source"]
    if src.get("url"):
        ref = {"type": "vcs" if src["type"] in ("git", "marketplace") else "distribution", "url": src["url"]}
        if src.get("ref"):
            ref["comment"] = f"ref {src['ref']}"
        out["externalReferences"] = [ref]

    # Where it was found: one occurrence per installation.
    out["evidence"] = {"occurrences": [
        {"location": f"{i['host']}:{i['path']}",
         "additionalContext": f"installScope={i['installScope']}" + (f", platform={i['platform']}" if i.get("platform") else "")}
        for i in c["installations"]]}

    props = [_prop("kind", c["kind"]), _prop("source.type", src["type"]),
             _prop("license.status", lic["status"])]
    best = [e for e in lic.get("evidence", []) if e.get("expression") == lic["expression"]]
    if best:
        top = max(best, key=lambda e: e.get("confidence", 0))
        props.append(_prop("license.source", top["source"]))
        if "confidence" in top:
            props.append(_prop("license.confidence", top["confidence"]))
    if src.get("marketplace"):
        props.append(_prop("source.marketplace", src["marketplace"]))
    if c.get("integrity"):
        props.append(_prop("integrity", c["integrity"]))
    if c.get("entitlement"):
        props.append(_prop("entitlement.status", c["entitlement"]["status"]))
    props.append(_prop("hosts", len({i["host"] for i in c["installations"]})))
    out["properties"] = props
    return out


def to_cyclonedx(bom: dict) -> dict:
    meta = bom["metadata"]
    tool = _tool()
    md = {"timestamp": meta["timestamp"], "tools": {"components": [tool]}}
    props = [_prop("specVersion", bom["specVersion"]), _prop("hosts", bom["summary"].get("hosts", len(meta["scope"]["hosts"])))]
    if meta["scope"].get("organization"):
        md["supplier"] = {"name": meta["scope"]["organization"]}
    if meta.get("policy", {}).get("id"):
        props.append(_prop("policy", meta["policy"]["id"] + (f"@{meta['policy']['version']}" if meta["policy"].get("version") else "")))
    md["properties"] = props

    refs = {c["bomRef"] for c in bom["components"]}
    deps: dict[str, set[str]] = {}
    for d in bom.get("dependencies", []):
        deps.setdefault(d["ref"], set()).update(x for x in d["dependsOn"] if x in refs)

    out = {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": bom["serialNumber"],
        "version": 1,
        "metadata": md,
        "components": [_component(c) for c in bom["components"]],
        "dependencies": [{"ref": r, "dependsOn": sorted(v)} for r, v in sorted(deps.items()) if r in refs],
    }
    findings = bom.get("findings", [])
    if findings:
        out["annotations"] = [{
            "bom-ref": f"finding-{f['id']}",
            "subjects": f["components"],
            "annotator": {"component": tool},
            "timestamp": meta["timestamp"],
            "text": f"[{f['severity']}] {f['rule']}: {f['message']}" + (f" Fix: {f['remediation']}" if f.get("remediation") else ""),
        } for f in findings]
    return out
