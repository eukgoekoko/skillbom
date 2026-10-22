#!/usr/bin/env python3
"""Validate example files (or given files) against the JSON Schemas in schema/.

Usage: python scripts/validate.py [FILE ...]
Schema is chosen by path: files under */skill-license/* or named skill-license.* use
the license schema, everything else the Skill BOM schema.
"""
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = {
    "license": ROOT / "schema/skill-license.schema.json",
    "bom": ROOT / "schema/skill-bom.schema.json",
}


def schema_for(path: Path) -> str:
    if "skill-license" in path.parts or path.name.startswith("skill-license."):
        return "license"
    return "bom"


def load(path: Path):
    text = path.read_text()
    return yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)


def main(argv):
    files = [Path(a) for a in argv] or sorted((ROOT / "examples").rglob("*.*"))
    validators = {
        k: Draft202012Validator(json.loads(p.read_text()), format_checker=FormatChecker())
        for k, p in SCHEMAS.items()
    }
    failed = 0
    for f in files:
        errors = sorted(validators[schema_for(f)].iter_errors(load(f)), key=lambda e: list(e.path))
        if errors:
            failed += 1
            print(f"FAIL {f}")
            for e in errors:
                print(f"  /{'/'.join(map(str, e.path))}: {e.message}")
        else:
            print(f"ok   {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
