#!/usr/bin/env python3
"""Publish the corpus study's aggregates and charts from .corpus/ results.

Writes docs/research/corpus-2026-10-summary.json (aggregate numbers only, no repository
names) and docs/_includes/charts/*.html, which docs/research/corpus-2026-10.md includes.
Re-run after analyze.py / accuracy.py so the published numbers and charts stay in sync.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

from skillbom.spdx import CATEGORIES, category

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".corpus"
SUMMARY = ROOT / "docs/research/corpus-2026-10-summary.json"
CHARTS = ROOT / "docs/_includes/charts"
OWN = ("skill-frontmatter", "text-match", "plugin-manifest", "skill-body")


def pct(n: int, total: int) -> float:
    return round(100 * n / total, 1)


def license_source(stats: dict) -> dict:
    rf, n = stats["resolvedFrom"], stats["count"]
    own = sum(rf.get(k, 0) for k in OWN)
    part = lambda c: {"count": c, "pct": pct(c, n)}
    return {"skills": n, "own": part(own), "parentManifest": part(rf.get("parent-manifest", 0)),
            "repoLicenseFile": part(rf.get("repo-license-file", 0)), "none": part(rf.get("none", 0))}


FIXED_REFS = {"LicenseRef-proprietary", "LicenseRef-custom", "LicenseRef-commons-clause"}
SIZE_BINS = [(1, 1, "1"), (2, 5, "2–5"), (6, 20, "6–20"), (21, 100, "21–100"), (101, 1000, "101–1,000"),
             (1001, 10**9, "more than 1,000")]


def _public_expression(expr: str) -> str:
    """Organization-specific LicenseRef ids can name a project; publish them only as a group."""
    def repl(m):
        return m.group(0) if m.group(0) in FIXED_REFS else "LicenseRef-(organization-specific)"
    return re.sub(r"LicenseRef-[A-Za-z0-9.-]+", repl, expr)


def _source_kind(c: dict) -> str:
    lic = c["license"]
    best = [e for e in lic.get("evidence", []) if e.get("expression") == lic["expression"]]
    if lic["expression"] == "NOASSERTION" or not best:
        return "none"
    top = max(best, key=lambda e: e.get("confidence", 0))["source"]
    if top in OWN or top == "skill-license-file":
        return "own"
    return "parentManifest" if top == "parent-manifest" else "repoLicenseFile"


def drilldown() -> dict:
    """Aggregates for the study's data explorer: counts only, no repository names."""
    seen: set[str] = set()
    skills_by = Counter()                   # (category, expression) -> distinct skills
    repos_by: dict[tuple, set] = defaultdict(set)  # (category, expression) -> repos (counted, never published)
    repos_by_cat: dict[str, set] = defaultdict(set)
    cross = Counter()                       # (category, source kind) -> distinct skills
    sizes = []
    for f in sorted((CORPUS / "boms").glob("*.json")):
        skills = [c for c in json.loads(f.read_text())["components"] if c["kind"] == "skill"]
        if not skills:
            continue
        sizes.append(len(skills))
        for c in skills:
            cat, expr = category(c["license"]["expression"]), _public_expression(c["license"]["expression"])
            repos_by[(cat, expr)].add(f.stem)
            repos_by_cat[cat].add(f.stem)
            if c["bomRef"] not in seen:
                seen.add(c["bomRef"])
                skills_by[(cat, expr)] += 1
                cross[(cat, _source_kind(c))] += 1
    repos_total = len(sizes)
    cats = []
    for cat in CATEGORIES:
        rows = sorted(((e, n, len(repos_by[(cc, e)])) for (cc, e), n in skills_by.items() if cc == cat),
                      key=lambda r: (-r[2], -r[1], r[0]))
        if not rows:
            continue
        top, rest = rows[:12], rows[12:]
        licenses = [{"expression": e, "skills": n, "repos": r} for e, n, r in top]
        if rest:
            licenses.append({"expression": f"{len(rest)} other licenses", "skills": sum(r[1] for r in rest),
                             "repos": None, "other": True})
        cats.append({"category": cat, "skills": sum(r[1] for r in rows), "repos": len(repos_by_cat[cat]),
                     "licenses": licenses})
    kinds = ["own", "parentManifest", "repoLicenseFile", "none"]
    bins = [{"bin": label, "repos": sum(1 for x in sizes if lo <= x <= hi),
             "skills": sum(x for x in sizes if lo <= x <= hi)} for lo, hi, label in SIZE_BINS]
    return {
        "skills": len(seen),
        "repos": repos_total,
        "categories": cats,
        "sourceByCategory": {c["category"]: {k: cross[(c["category"], k)] for k in kinds} for c in cats},
        "skillsPerRepo": {"median": sorted(sizes)[len(sizes) // 2], "bins": bins},
    }


def summary() -> dict:
    a = json.loads((CORPUS / "analysis.json").read_text())
    s = a["skills"]
    # The training round is history: it scored the scanner *before* the fixes it led to.
    # accuracy/results.json now holds a re-score after the fixes, so the blind numbers are fixed here.
    acc = {"training": {"n": 200, "ambiguous": 4, "scanner": "before the accuracy fixes",
                        "licenseAccuracy": 94.5, "licenseAccuracyUnambiguous": 96.4, "categoryAccuracy": 97.0,
                        "ownAgreement": 99.5, "noLicense": {"precision": 81.8, "recall": 100.0}}}
    r = json.loads((CORPUS / "accuracy/holdout/results.json").read_text())
    acc["holdout"] = {"scanner": "after the accuracy fixes",
                      **{k: r[k] for k in ("n", "ambiguous", "licenseAccuracy", "licenseAccuracyUnambiguous",
                                           "categoryAccuracy", "ownAgreement")},
                      "noLicense": {k: r["noLicense"][k] for k in ("precision", "recall")}}
    return {
        "study": "License landscape of public agent skills, October 2026",
        "url": "https://eukgoekoko.github.io/skillbom/research/corpus-2026-10.html",
        "repos": a["repos"],
        "skills": s["count"],
        "plugins": a["plugins"]["count"],
        "licenseSource": license_source(s),
        "licenseSourceOfficialMarketplace": license_source(a["skillsOfficialMarketplace"]),
        "skillCategories": s["categories"],
        "byRepo": a["byRepo"],
        "byRepoOfficialMarketplace": a["byRepoOfficialMarketplace"],
        "frontmatterLicensePct": s["frontmatterLicensePct"],
        "anthropicProprietaryCopies": {"repos": a["anthropicProprietaryCopies"]["repos"],
                                       "copies": a["anthropicProprietaryCopies"]["skills"]},
        "accuracy": acc,
        "drilldown": drilldown(),
    }


def bars(rows: list[tuple[str, float, str]], scale: float, unit: str = "%", series: str = "s1") -> str:
    out = []
    for label, value, tip in rows:
        width = max(100 * value / scale, 0.6)
        out.append(
            f'<div class="chart-row" tabindex="0" data-tip="{escape(tip)}">'
            f'<span class="chart-label">{escape(label)}</span>'
            f'<span class="chart-track"><span class="chart-bar {series}" style="width:{width:.2f}%"></span></span>'
            f'<span class="chart-value">{value:.1f}{unit}</span></div>')
    return "\n".join(out)



def figure(fid: str, title: str, sub: str, body: str, note: str, legend: str = "") -> str:
    return (f'<figure class="chart" id="{fid}" data-chart="{fid.removeprefix("chart-")}" '
            f'data-src="corpus-2026-10-summary.json">\n<figcaption><b>{escape(title)}</b><span>{escape(sub)}</span></figcaption>\n'
            f'{legend}<div class="chart-bars" role="img" aria-label="{escape(title)}">\n{body}\n</div>\n'
            f'<p class="chart-note">{escape(note)}</p>\n</figure>\n')


def charts(d: dict) -> dict[str, str]:
    ls, n = d["licenseSource"], d["skills"]
    rows = [("Parent plugin manifest", ls["parentManifest"]["pct"], ls["parentManifest"]["count"]),
            ("Repository LICENSE file", ls["repoLicenseFile"]["pct"], ls["repoLicenseFile"]["count"]),
            ("The skill itself", ls["own"]["pct"], ls["own"]["count"]),
            ("No license anywhere", ls["none"]["pct"], ls["none"]["count"])]
    source = figure(
        "chart-license-source", "Where a skill's license comes from",
        f"Share of {n:,} public skills, by the evidence their license was resolved from",
        bars([(l, p, f"{l}: {c:,} of {n:,} skills ({p}%)") for l, p, c in rows], 100),
        "The first two rows are licenses a skill inherits from its surroundings. 'The skill itself' covers SKILL.md frontmatter, "
        "a License section in SKILL.md, and license files in the skill's own folder.")

    r, m = d["byRepo"], d["byRepoOfficialMarketplace"]
    kinds = [("No license at all", "anyUnlicensedPct"), ("Copyleft", "anyCopyleftPct"),
             ("Proprietary", "anyProprietaryPct"), ("Non-commercial", "anyNonCommercialPct"),
             ("Source-available", "anySourceAvailablePct"), ("Custom terms", "anyCustomPct")]
    restrictive = figure(
        "chart-restrictive", "Repositories with at least one skill under…",
        f"Share of the {r['repos']:,} repositories that contain skills",
        bars([(l, r[k], f"{l}: {r[k]}% of {r['repos']:,} repositories") for l, k in kinds], max(r[k] for _, k in kinds)),
        "One repository can count in several rows. Bars are scaled to the largest value.")

    measures = [("License every skill individually", "allSkillsOwnLicensePct"),
                ("Contain a skill with no license", "anyUnlicensedPct")]
    rows_html = []
    for label, k in measures:
        rows_html.append(f'<div class="chart-group"><span class="chart-group-label">{escape(label)}</span>')
        rows_html.append(bars([("All repositories", r[k], f"All {r['repos']:,} repositories: {r[k]}%")], 25, series="s1"))
        rows_html.append(bars([("Official marketplace", m[k], f"Official marketplace ({m['repos']} repositories): {m[k]}%")], 25, series="s2"))
        rows_html.append("</div>")
    legend = ('<p class="chart-legend"><span><i class="s1"></i>All repositories</span>'
              '<span><i class="s2"></i>Official Claude Code marketplace</span></p>\n')
    marketplace = figure(
        "chart-marketplace", "Licensing practices: official marketplace vs. all repositories",
        f"All {r['repos']:,} repositories with skills vs. the {m['repos']} from the official marketplace",
        "\n".join(rows_html),
        "Bars on a 0–25% scale.", legend)
    return {"license-source.html": source, "restrictive.html": restrictive, "marketplace.html": marketplace}


CATEGORY_LABELS = {"permissive": "Permissive", "copyleft": "Copyleft", "source-available": "Source-available",
                   "non-commercial": "Non-commercial", "proprietary": "Proprietary", "custom": "Custom terms",
                   "other": "Other terms", "none": "No license"}


def study_parts(d: dict) -> dict[str, str]:
    """Header cards, method funnel and the explorer's no-JS fallback for the study page."""
    ls, r, acc = d["licenseSource"], d["byRepo"], d["accuracy"]["holdout"]
    inherited = round(ls["parentManifest"]["pct"] + ls["repoLicenseFile"]["pct"], 1)
    cards = [
        (f"{inherited}%", "of public skills are licensed only through the repository or plugin they sit in"),
        (f"{r['anyUnlicensedPct']}%", "of repositories ship at least one skill with no license at all"),
        (f"{d['skillCategories'].get('non-commercial', [0])[0]:,}", "skills don't permit commercial use"),
        (f"{d['anthropicProprietaryCopies']['copies']}", f"copies of proprietary skills in "
                                                         f"{d['anthropicProprietaryCopies']['repos']} public collections"),
    ]
    header = '<div class="study-stats">\n' + "\n".join(
        f'<div class="study-stat"><b>{escape(v)}</b><span>{escape(t)}</span></div>' for v, t in cards) + "\n</div>\n"

    steps = [(f"{d['repos']['scanned'] + 16:,}", "candidate repositories"), (f"{d['repos']['scanned']:,}", "fetched"),
             (f"{d['repos']['withSkills']:,}", "contain skills"), (f"{d['skills']:,}", "distinct skills scanned"),
             (f"{d['accuracy']['training']['n'] + acc['n']}", "hand-labeled for accuracy")]
    method = '<ol class="method-flow">\n' + "\n".join(
        f'<li><b>{escape(v)}</b><span>{escape(t)}</span></li>' for v, t in steps) + "\n</ol>\n"

    dd = d["drilldown"]
    rows = "".join(f'<tr><td>{escape(CATEGORY_LABELS[c["category"]])}</td><td class="num">{c["skills"]:,}</td>'
                   f'<td class="num">{c["repos"]:,}</td><td>{escape(", ".join(l["expression"] for l in c["licenses"][:3]))}</td></tr>'
                   for c in dd["categories"])
    explorer = (f'<div class="explorer" data-explorer="corpus-2026-10-summary.json">\n'
                f'<table><thead><tr><th>category</th><th>skills</th><th>repositories</th><th>most common licenses</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>\n'
                f'<p class="chart-note">Enable JavaScript to drill into each category. The numbers are also in '
                f'<a href="corpus-2026-10-summary.json">the summary JSON</a>.</p>\n</div>\n')
    samples = ('<div class="sample-browser" data-samples="accuracy-train-2026-10.csv accuracy-holdout-2026-10.csv">\n'
               '<p>The 300 hand-labeled skills are in two tables: <a href="accuracy-train-2026-10.csv">training set</a> '
               'and <a href="accuracy-holdout-2026-10.csv">held-out set</a> (CSV). Enable JavaScript to search and filter them here.</p>\n</div>\n')
    size, total = dd["skillsPerRepo"], sum(b["skills"] for b in dd["skillsPerRepo"]["bins"])
    big = size["bins"][-1]
    rows = [(b["bin"], pct(b["repos"], dd["repos"]), f'{b["bin"]} skills: {b["repos"]:,} repositories '
             f'({pct(b["repos"], dd["repos"])}%), holding {b["skills"]:,} skills') for b in size["bins"]]
    sizes = figure("chart-repo-size", "Skills per repository",
                   f"Share of the {dd['repos']:,} repositories that contain skills, by how many they contain",
                   bars(rows, 50),
                   f"Median: {size['median']} skills per repository. The {big['repos']} repositories with more than 1,000 "
                   f"skills together hold {pct(big['skills'], total):.0f}% of all skills, which is why this study leads "
                   "with per-repository numbers.")
    return {"study-header.html": header, "method.html": method, "explorer.html": explorer, "samples.html": samples,
            "repo-size.html": sizes}


def main() -> int:
    d = summary()
    SUMMARY.write_text(json.dumps(d, indent=2) + "\n")
    CHARTS.mkdir(parents=True, exist_ok=True)
    parts = {**charts(d), **study_parts(d)}
    for name, html in parts.items():
        (CHARTS / name).write_text(html)
    print(f"wrote {SUMMARY.relative_to(ROOT)} and {len(parts)} includes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
