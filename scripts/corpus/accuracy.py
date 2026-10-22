#!/usr/bin/env python3
"""Compare the scanner's verdicts with the blind labels from sample.py.

Reads <dir>/sample.jsonl and labels.txt plus the per-repo BOMs, writes <dir>/results.json
and, with --csv, the published label table. Usage:
  accuracy.py [--name holdout] [--csv docs/research/accuracy-labels-2026-10.csv]
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from skillbom import spdx
from skillbom.licenses import INHERITED_SOURCES

ROOT = Path(__file__).resolve().parents[2]
TRUTH_SPECIAL = {"NONE": spdx.NOASSERTION, "PROPRIETARY": spdx.PROPRIETARY, "CUSTOM": spdx.CUSTOM}


def family(expr: str) -> list[frozenset[str]]:
    """DNF choices with GNU -only/-or-later folded together (license texts don't say which)."""
    if expr in (spdx.NOASSERTION,):
        return []
    fold = lambda i: re.sub(r"-(only|or-later)$", "", i)
    return sorted({frozenset(fold(i) for i in c) for c in spdx.choices(expr)}, key=sorted)


def same_license(truth: str, found: str) -> bool:
    if truth == spdx.CUSTOM:
        return found.startswith("LicenseRef-") and found != spdx.PROPRIETARY
    if truth in (spdx.NOASSERTION, spdx.PROPRIETARY):
        return found == truth
    try:
        return family(truth) == family(found)
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="")
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()
    ACC = ROOT / ".corpus/accuracy" / args.name
    sample = [json.loads(l) for l in (ACC / "sample.jsonl").read_text().splitlines()]
    labels = {}
    for line in (ACC / "labels.txt").read_text().splitlines():
        if line[:1] in ("S", "H"):
            sid, truth, own, note = line.split("|", 3)
            expr = TRUTH_SPECIAL.get(truth) or spdx.normalize(truth)
            if expr is None:
                raise SystemExit(f"{sid}: label {truth!r} is not a valid SPDX expression")
            labels[sid] = {"truth": expr, "own": own == "y", "note": note}

    rows, boms = [], {}
    for s in sample:
        bom = boms.setdefault(s["repo"], json.loads((ROOT / ".corpus/boms" / f"{s['repo']}.json").read_text()))
        comp = next(c for c in bom["components"] if c["bomRef"] == s["bomRef"])
        lic = comp["license"]
        best = [e for e in lic.get("evidence", []) if e.get("expression") == lic["expression"]]
        own_found = any(e["source"] not in INHERITED_SOURCES for e in best)
        lab = labels[s["id"]]
        rows.append({
            "id": s["id"], "repo": s["repo"].replace("__", "/", 1), "path": "/" + s["path"],
            "truth": lab["truth"], "truth_category": spdx.category(lab["truth"]), "truth_own": lab["own"],
            "found": lic["expression"], "found_category": spdx.category(lic["expression"]), "found_own": own_found,
            "license_match": same_license(lab["truth"], lic["expression"]),
            "ambiguous": "AMBIGUOUS" in lab["note"], "note": lab["note"].replace("AMBIGUOUS: ", ""),
        })

    n = len(rows)
    clear = [r for r in rows if not r["ambiguous"]]
    pct = lambda k, rs: round(100 * sum(1 for r in rs if k(r)) / len(rs), 1)
    none_t = [r for r in rows if r["truth"] == spdx.NOASSERTION]
    none_f = [r for r in rows if r["found"] == spdx.NOASSERTION]
    both_none = sum(1 for r in none_t if r["found"] == spdx.NOASSERTION)
    results = {
        "n": n, "ambiguous": n - len(clear),
        "licenseAccuracy": pct(lambda r: r["license_match"], rows),
        "licenseAccuracyUnambiguous": pct(lambda r: r["license_match"], clear),
        "categoryAccuracy": pct(lambda r: r["truth_category"] == r["found_category"], rows),
        "ownAgreement": pct(lambda r: r["truth_own"] == r["found_own"], rows),
        "ownTruthPct": pct(lambda r: r["truth_own"], rows),
        "ownFoundPct": pct(lambda r: r["found_own"], rows),
        "noLicense": {"truth": len(none_t), "found": len(none_f), "agree": both_none,
                      "precision": round(100 * both_none / len(none_f), 1) if none_f else None,
                      "recall": round(100 * both_none / len(none_t), 1) if none_t else None},
        "confusion": Counter(f'{r["truth_category"]} -> {r["found_category"]}' for r in rows
                             if r["truth_category"] != r["found_category"]),
        "truthCategories": Counter(r["truth_category"] for r in rows),
        "disagreements": [r for r in rows if not r["license_match"]],
        "ownDisagreements": [r for r in rows if r["truth_own"] != r["found_own"]],
    }
    (ACC / "results.json").write_text(json.dumps(results, indent=2))
    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "repo", "path", "truth", "truth_category", "truth_own",
                                              "found", "found_category", "found_own", "license_match",
                                              "ambiguous", "note"])
            w.writeheader()
            w.writerows(rows)
    print(json.dumps({k: v for k, v in results.items() if k not in ("disagreements", "ownDisagreements")}, indent=2))
    print("\nlicense disagreements:")
    for r in results["disagreements"]:
        print(f'  {r["id"]} {r["repo"]}{r["path"]}: truth {r["truth"]} | found {r["found"]}'
              f'{"  (ambiguous)" if r["ambiguous"] else ""}  {r["note"]}')
    print("\nown-license disagreements:")
    for r in results["ownDisagreements"]:
        print(f'  {r["id"]} {r["repo"]}{r["path"]}: truth own={r["truth_own"]} found own={r["found_own"]}  {r["note"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
