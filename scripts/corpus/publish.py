#!/usr/bin/env python3
"""Publish the corpus study's aggregates and charts from .corpus/ results.

Writes docs/research/corpus-2026-10-summary.json (aggregate numbers only, no repository
names) and docs/_includes/charts/*.html, which docs/research/corpus-2026-10.md includes.
Re-run after analyze.py / accuracy.py so the published numbers and charts stay in sync.
"""
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".corpus"
SUMMARY = ROOT / "docs/research/corpus-2026-10-summary.json"
CHARTS = ROOT / "docs/_includes/charts"
OWN = ("skill-frontmatter", "text-match", "plugin-manifest", "skill-body")


def pct(n: int, total: int) -> float:
    return round(100 * n / total, 1)


def summary() -> dict:
    a = json.loads((CORPUS / "analysis.json").read_text())
    s = a["skills"]
    rf, n = s["resolvedFrom"], s["count"]
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
        "skills": n,
        "plugins": a["plugins"]["count"],
        "licenseSource": {
            "own": {"count": sum(rf.get(k, 0) for k in OWN), "pct": pct(sum(rf.get(k, 0) for k in OWN), n)},
            "parentManifest": {"count": rf.get("parent-manifest", 0), "pct": pct(rf.get("parent-manifest", 0), n)},
            "repoLicenseFile": {"count": rf.get("repo-license-file", 0), "pct": pct(rf.get("repo-license-file", 0), n)},
            "none": {"count": rf.get("none", 0), "pct": pct(rf.get("none", 0), n)},
        },
        "skillCategories": s["categories"],
        "byRepo": a["byRepo"],
        "byRepoOfficialMarketplace": a["byRepoOfficialMarketplace"],
        "frontmatterLicensePct": s["frontmatterLicensePct"],
        "anthropicProprietaryCopies": {"repos": a["anthropicProprietaryCopies"]["repos"],
                                       "copies": a["anthropicProprietaryCopies"]["skills"]},
        "accuracy": acc,
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


def table(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<details class="chart-table"><summary>Show as table</summary><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></details>'


def figure(fid: str, title: str, sub: str, body: str, tbl: str, note: str, legend: str = "") -> str:
    return (f'<figure class="chart" id="{fid}">\n<figcaption><b>{escape(title)}</b><span>{escape(sub)}</span></figcaption>\n'
            f'{legend}<div class="chart-bars" role="img" aria-label="{escape(title)}">\n{body}\n</div>\n{tbl}\n'
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
        table(["license comes from", "skills", "share"], [[l, f"{c:,}", f"{p}%"] for l, p, c in rows]),
        "Inherited: the first two rows, 81.3% together. 'The skill itself' covers SKILL.md frontmatter, "
        "a License section in SKILL.md, and license files in the skill's own folder.")

    r, m = d["byRepo"], d["byRepoOfficialMarketplace"]
    kinds = [("No license at all", "anyUnlicensedPct"), ("Copyleft", "anyCopyleftPct"),
             ("Proprietary", "anyProprietaryPct"), ("Non-commercial", "anyNonCommercialPct"),
             ("Source-available", "anySourceAvailablePct"), ("Custom terms", "anyCustomPct")]
    restrictive = figure(
        "chart-restrictive", "Repositories with at least one skill under…",
        f"Share of the {r['repos']:,} repositories that contain skills",
        bars([(l, r[k], f"{l}: {r[k]}% of {r['repos']:,} repositories") for l, k in kinds], max(r[k] for _, k in kinds)),
        table(["license type", "share of repositories"], [[l, f"{r[k]}%"] for l, k in kinds]),
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
        table(["measure", "all repositories", "official marketplace"], [[l, f"{r[k]}%", f"{m[k]}%"] for l, k in measures]),
        "Bars on a 0–25% scale.", legend)
    return {"license-source.html": source, "restrictive.html": restrictive, "marketplace.html": marketplace}


def main() -> int:
    d = summary()
    SUMMARY.write_text(json.dumps(d, indent=2) + "\n")
    CHARTS.mkdir(parents=True, exist_ok=True)
    for name, html in charts(d).items():
        (CHARTS / name).write_text(html)
    print(f"wrote {SUMMARY.relative_to(ROOT)} and {len(charts(d))} charts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
