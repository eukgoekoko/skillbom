#!/usr/bin/env python3
"""Run the scanner over every cloned corpus repository and aggregate license statistics.

Writes .corpus/boms/<repo>.json per repository and .corpus/results.json with the
aggregates; prints a Markdown summary to stdout.
"""
import json
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

from skillbom import discover
from skillbom.spdx import category
from skillbom.bom import build
from skillbom.licenses import INHERITED_SOURCES, license_files

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".corpus"
# Marker phrase of the license that ships with Anthropic's proprietary document skills.
ANTHROPIC_TERMS = "governed by your agreement with anthropic"


def scan_repo(repo_dir: str) -> dict | None:
    d = Path(repo_dir)
    try:
        cands = discover.scan_tree(d, "claude-code", "local")
        bom = build(cands, roots=[d], home=d, host="corpus")
    except Exception as e:  # keep going; report the failure
        return {"repo": d.name, "error": f"{type(e).__name__}: {e}"}
    (CORPUS / "boms" / f"{d.name}.json").write_text(json.dumps(bom))
    anthropic_terms = set()
    for c in cands:
        for f in license_files(c.path):
            try:
                if ANTHROPIC_TERMS in " ".join(f.read_text(errors="replace").lower().split()):
                    anthropic_terms.add(c.name)
            except OSError:
                pass
    root_files = license_files(d)
    return {"repo": d.name, "bom": bom, "root_license": bool(root_files), "anthropic_terms": sorted(anthropic_terms)}


def main() -> int:
    sources = {json.loads(l)["repo"].replace("/", "__"): json.loads(l)
               for l in (CORPUS / "sources.jsonl").read_text().splitlines()}
    # Only repositories whose clone finished (fetch.py logs each one), so this can run mid-fetch.
    fetched = {json.loads(l)["repo"].replace("/", "__") for l in (CORPUS / "fetch.jsonl").read_text().splitlines()
               if json.loads(l)["ok"]}
    repos = sorted(str(CORPUS / "repos" / r) for r in fetched)
    (CORPUS / "boms").mkdir(exist_ok=True)
    with Pool() as pool:
        results = [r for r in pool.imap_unordered(scan_repo, repos, chunksize=4) if r]

    errors = [r for r in results if "error" in r]
    results = [r for r in results if "error" not in r]
    with_skills = [r for r in results if r["bom"]["summary"]["byKind"].get("skill")]

    # Distinct components across the corpus, keyed by bomRef (kind + content hash).
    comps: dict[str, dict] = {}
    repos_of: dict[str, set] = defaultdict(set)
    marketplace_refs: set[str] = set()
    for r in results:
        official = "official-marketplace" in sources.get(r["repo"], {}).get("origins", [])
        for c in r["bom"]["components"]:
            comps.setdefault(c["bomRef"], c)
            repos_of[c["bomRef"]].add(r["repo"])
            if official:
                marketplace_refs.add(c["bomRef"])

    skills = {k: c for k, c in comps.items() if c["kind"] == "skill"}

    def best_source(c):
        ev = [e for e in c["license"].get("evidence", []) if e.get("expression") == c["license"]["expression"]]
        own = [e for e in ev if e["source"] not in INHERITED_SOURCES]
        pick = max(own or ev, key=lambda e: e.get("confidence", 0), default=None)
        return pick["source"] if pick else "none"

    def stats(cs: dict) -> dict:
        n = len(cs) or 1
        cats = Counter(category(c["license"]["expression"]) for c in cs.values())
        src = Counter(best_source(c) for c in cs.values())
        own = sum(1 for c in cs.values() if best_source(c) not in INHERITED_SOURCES | {"none"})
        fm = [c for c in cs.values() if any(e["source"] == "skill-frontmatter" for e in c["license"].get("evidence", []))]
        fm_free = [c for c in fm if any(e["source"] == "skill-frontmatter" and "value" in e
                                        for e in c["license"]["evidence"])]
        return {
            "count": len(cs),
            "categories": {k: [v, round(100 * v / n, 1)] for k, v in cats.most_common()},
            "resolvedFrom": dict(src.most_common()),
            "ownLicensePct": round(100 * own / n, 1),
            "frontmatterLicensePct": round(100 * len(fm) / n, 1),
            "frontmatterFreeTextPct": round(100 * len(fm_free) / max(len(fm), 1), 1),
            "licenseFileAdoption": sum(1 for c in cs.values() if c["license"]["status"] == "declared"),
            "topExpressions": Counter(c["license"]["expression"] for c in cs.values()).most_common(12),
        }

    # Per-repository view: one vote per repo, so a repo with 300 skills doesn't dominate.
    def repo_view(rs):
        n = len(rs) or 1
        cats = [Counter(category(c["license"]["expression"]) for c in r["bom"]["components"] if c["kind"] == "skill")
                for r in rs]
        own = [all(best_source(c) not in INHERITED_SOURCES | {"none"}
                   for c in r["bom"]["components"] if c["kind"] == "skill") for r in rs]
        counts = sorted(r["bom"]["summary"]["byKind"].get("skill", 0) for r in rs)
        pct = lambda k: round(100 * sum(1 for c in cats if c.get(k)) / n, 1)
        return {"repos": len(rs), "medianSkills": counts[len(counts) // 2] if counts else 0,
                "anyUnlicensedPct": pct("none"), "anyNonCommercialPct": pct("non-commercial"),
                "anySourceAvailablePct": pct("source-available"), "anyCopyleftPct": pct("copyleft"),
                "anyProprietaryPct": pct("proprietary"), "anyCustomPct": pct("custom"),
                "allSkillsOwnLicensePct": round(100 * sum(own) / n, 1)}

    findings = Counter()
    for r in results:
        for f in r["bom"]["findings"]:
            findings[f["rule"]] += 1

    copied = {k: v for k, v in repos_of.items() if len(v) > 1 and k in skills}
    anthropic_copies = sorted((r["repo"], n) for r in results for n in r["anthropic_terms"]
                              if not r["repo"].startswith("anthropics__"))

    # Detector gaps: license files we couldn't identify, declared values we couldn't parse.
    unparsed_values, unrecognized_files = Counter(), Counter()
    for c in comps.values():
        for e in c["license"].get("evidence", []):
            if "value" in e and "expression" not in e:
                unparsed_values[e["value"][:80]] += 1
            if e["source"] in ("text-match", "repo-license-file") and "expression" not in e:
                unrecognized_files[Path(e["path"]).name] += 1

    out = {
        "repos": {"scanned": len(results), "withSkills": len(with_skills), "errors": len(errors),
                  "withRootLicensePct": round(100 * sum(r["root_license"] for r in with_skills) / max(len(with_skills), 1), 1)},
        "byRepo": repo_view(with_skills),
        "byRepoOfficialMarketplace": repo_view([r for r in with_skills
                                                if "official-marketplace" in sources.get(r["repo"], {}).get("origins", [])]),
        "skills": stats(skills),
        "skillsOfficialMarketplace": stats({k: v for k, v in skills.items() if k in marketplace_refs}),
        "plugins": stats({k: c for k, c in comps.items() if c["kind"] == "plugin"}),
        "installationsPerDistinctSkill": round(sum(len(repos_of[k]) for k in skills) / max(len(skills), 1), 2),
        "copiedSkills": {"distinct": len(copied), "maxRepos": max((len(v) for v in copied.values()), default=0)},
        "anthropicProprietaryCopies": {"repos": len({r for r, _ in anthropic_copies}), "skills": len(anthropic_copies),
                                       "sample": anthropic_copies[:20]},
        "findings": dict(findings.most_common()),
        "detectorGaps": {"unparsedValues": unparsed_values.most_common(25),
                         "unrecognizedLicenseFiles": unrecognized_files.most_common(10)},
        "errors": errors[:20],
    }
    (CORPUS / "results.json").write_text(json.dumps(out, indent=2))
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
