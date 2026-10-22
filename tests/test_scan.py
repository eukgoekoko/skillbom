import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from skillbom.cli import main
from skillbom.hashing import content_hash

ROOT = Path(__file__).resolve().parent.parent
APACHE = "Apache License\nVersion 2.0, January 2004\n"
MIT = 'Permission is hereby granted, free of charge ... THE SOFTWARE IS PROVIDED "AS IS"'
GPL3 = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def skill(directory: Path, name: str, extra: str = "") -> Path:
    write(directory / "SKILL.md", f"---\nname: {name}\ndescription: test\n{extra}---\n\n# {name}\n")
    return directory


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    skills = h / ".claude/skills"
    skill(skills / "alpha", "alpha", "license: MIT\n")
    skill(skills / "beta", "beta")
    gpl = skill(skills / "gpl-skill", "gpl-skill")
    write(gpl / "LICENSE", GPL3)
    nc = skill(skills / "nc", "nc")
    write(nc / "skill-license.yaml", """specVersion: "0.1"
subject: {kind: skill, id: acme/nc, version: 1.0.0, contentHash: {alg: sha256, value: "%s"}}
license: {expression: CC-BY-NC-4.0}
""" % ("0" * 64))
    prop = skill(skills / "synced/org_acct/pdf", "pdf", "license: Proprietary. LICENSE.txt has complete terms\n")
    write(prop / "LICENSE.txt", "(c) 2025 Example. All rights reserved.")
    conflict = skill(skills / "conflict", "conflict", "license: MIT\n")
    write(conflict / "LICENSE", APACHE)

    # Installed plugin with a nested skill, plus a marketplace clone containing it.
    mkt = h / ".claude/plugins/marketplaces/demo"
    write(mkt / "LICENSE", APACHE)
    write(mkt / ".claude-plugin/marketplace.json", json.dumps(
        {"name": "demo", "plugins": [{"name": "tool", "source": "./plugins/tool", "author": {"name": "Demo Inc"}}]}))
    plugin = mkt / "plugins/tool"
    write(plugin / ".claude-plugin/plugin.json", json.dumps({"name": "tool", "version": "1.2.3"}))
    skill(plugin / "skills/inner", "inner")
    bundle = skill(plugin / "skills/bundle", "bundle")
    write(bundle / "skill-license.yaml", """specVersion: "0.1"
subject: {kind: skill, id: demo/bundle, version: 1.0.0}
license: {expression: MIT}
includes:
  - {id: x/nd, version: 1.0.0, license: CC-BY-NC-ND-4.0, relation: modified}
  - {id: x/ok, version: 1.0.0, license: MIT, relation: bundled}
""")
    plugins = h / ".claude/plugins"
    write(plugins / "known_marketplaces.json", json.dumps({"demo": {"installLocation": str(mkt)}}))
    write(plugins / "installed_plugins.json", json.dumps(
        {"version": 2, "plugins": {"tool@demo": [{"scope": "user", "installPath": str(plugin), "version": "1.2.3"}]}}))
    write(h / ".claude/settings.json", json.dumps({"enabledPlugins": {"tool@demo": True}}))
    return h


def scan(tmp_path, *args) -> dict:
    out = tmp_path / "bom.json"
    assert main(["scan", "-q", "-o", str(out), *args]) == 0
    bom = json.loads(out.read_text())
    schema = json.loads((ROOT / "schema/skill-bom.schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(bom))
    assert not errors, errors
    return bom


def by_name(bom, name, kind="skill"):
    [c] = [c for c in bom["components"] if c["name"] == name and c["kind"] == kind]
    return c


def rules(bom, name):
    refs = {c["bomRef"] for c in bom["components"] if c["name"] == name}
    return sorted(f["rule"] for f in bom["findings"] if set(f["components"]) & refs)


def test_scan_home(home, tmp_path):
    policy = write(tmp_path / "policy.yaml", "id: test\ndeniedLicenses: [GPL-*, AGPL-*]\n")
    bom = scan(tmp_path, "--home", str(home), "--policy", str(policy))

    alpha = by_name(bom, "alpha")
    assert alpha["license"] == {"status": "inferred", "expression": "MIT", "evidence": [
        {"source": "skill-frontmatter", "path": "~/.claude/skills/alpha/SKILL.md", "expression": "MIT", "confidence": 0.9}]}
    assert alpha["entitlement"] == {"status": "not-required"}
    assert alpha["installations"][0]["path"] == "~/.claude/skills/alpha"
    assert rules(bom, "alpha") == []

    assert by_name(bom, "beta")["license"]["expression"] == "NOASSERTION"
    assert rules(bom, "beta") == ["license-unknown"]

    assert by_name(bom, "gpl-skill")["license"]["expression"] == "GPL-3.0-only"
    assert rules(bom, "gpl-skill") == ["license-denied"]

    nc = by_name(bom, "nc")
    assert nc["id"] == "acme/nc"
    assert nc["license"]["status"] == "declared"
    assert nc["integrity"] == "modified"
    assert nc["entitlement"]["status"] == "unknown"
    assert rules(bom, "nc") == ["commercial-use-restricted", "integrity-modified"]

    pdf = by_name(bom, "pdf")
    assert pdf["license"]["expression"] == "LicenseRef-proprietary"
    assert pdf["source"] == {"type": "registry", "url": "https://claude.ai"}
    assert rules(bom, "pdf") == []

    assert rules(bom, "conflict") == ["license-conflict"]

    tool = by_name(bom, "tool", "plugin")
    assert tool["version"] == "1.2.3" and tool["publisher"] == "Demo Inc"
    assert tool["source"] == {"type": "marketplace", "marketplace": "demo"}
    assert tool["installations"][0]["enabled"] is True
    # Installed plugins' boundary is their own dir, so the marketplace LICENSE isn't inherited.
    assert tool["license"]["expression"] == "NOASSERTION"
    assert rules(bom, "bundle") == ["composition-incompatible"]
    inner = by_name(bom, "inner")
    assert inner["installations"][0]["installScope"] == "plugin"
    assert {"ref": tool["bomRef"], "dependsOn": sorted([inner["bomRef"], by_name(bom, "bundle")["bomRef"]]),
            "relation": "contains"} in bom["dependencies"]

    assert bom["metadata"]["policy"] == {"id": "test", "deniedLicenses": ["GPL-*", "AGPL-*"]}
    assert bom["summary"]["components"] == len(bom["components"]) == 9
    assert [f["id"] for f in bom["findings"]] == [f"F{i}" for i in range(1, len(bom["findings"]) + 1)]
    assert bom["findings"][0]["severity"] == "critical"


def test_catalog_dedupes_and_inherits_repo_license(home, tmp_path):
    bom = scan(tmp_path, "--home", str(home), "--include-catalogs")
    tool = by_name(bom, "tool", "plugin")
    # Same content installed and in the catalog: one component, two installations.
    assert sorted(i["installScope"] for i in tool["installations"]) == ["catalog", "user"]
    # The license of the first occurrence (installed) is kept.
    assert tool["license"]["expression"] == "NOASSERTION"


def test_catalog_only(home, tmp_path):
    (home / ".claude/plugins/installed_plugins.json").unlink()
    bom = scan(tmp_path, "--home", str(home), "--include-catalogs")
    tool = by_name(bom, "tool", "plugin")
    assert tool["installations"][0]["installScope"] == "catalog"
    assert tool["license"]["expression"] == "Apache-2.0"
    assert tool["license"]["evidence"][0]["source"] == "repo-license-file"


def test_own_license_beats_repo_license(home, tmp_path):
    plugin = home / ".claude/plugins/marketplaces/demo/plugins/tool"
    write(plugin / "LICENSE", "(c) Demo Inc. All rights reserved.")
    (home / ".claude/plugins/installed_plugins.json").unlink()
    bom = scan(tmp_path, "--home", str(home), "--include-catalogs")
    assert by_name(bom, "tool", "plugin")["license"]["expression"] == "LicenseRef-proprietary"


def test_project_and_root(tmp_path):
    proj = tmp_path / "proj"
    skill(proj / ".claude/skills/p", "p")
    write(proj / "LICENSE", MIT)
    other = tmp_path / "other"
    skill(other / "deep/q", "q", "license: Apache-2.0\n")
    bom = scan(tmp_path, "--no-home", "--project", str(proj), "--root", str(other))
    p = by_name(bom, "p")
    assert p["installations"][0]["installScope"] == "project"
    assert p["license"]["expression"] == "MIT"
    assert p["license"]["evidence"][0]["source"] == "repo-license-file"
    assert by_name(bom, "q")["installations"][0]["installScope"] == "local"


def test_custom_license_needs_review(tmp_path):
    s = skill(tmp_path / "root/s", "s")
    write(s / "LICENSE", "ACME Skill License v1. You may use this skill only on Tuesdays.")
    bom = scan(tmp_path, "--no-home", "--root", str(tmp_path / "root"))
    assert by_name(bom, "s")["license"]["expression"] == "LicenseRef-custom"
    assert rules(bom, "s") == ["license-review"]


def test_declared_hash_match(tmp_path):
    s = skill(tmp_path / "root/s", "s")
    digest = content_hash(s)
    write(s / "skill-license.yaml", f"""specVersion: "0.1"
subject: {{kind: skill, id: a/s, version: 1.0.0, contentHash: {{alg: sha256, value: "{digest}"}}}}
license: {{expression: MIT}}
""")
    bom = scan(tmp_path, "--no-home", "--root", str(tmp_path / "root"))
    assert by_name(bom, "s")["integrity"] == "match"


def test_invalid_license_file(tmp_path):
    s = skill(tmp_path / "root/s", "s")
    write(s / "skill-license.yaml", "specVersion: '0.1'\nlicense: {expression: 'Proprietary stuff'}\n")
    bom = scan(tmp_path, "--no-home", "--root", str(tmp_path / "root"))
    assert rules(bom, "s") == ["license-invalid", "license-unknown"]


def test_html_report(home, tmp_path):
    html = tmp_path / "report.html"
    policy = write(tmp_path / "policy.yaml", "id: test\ndeniedLicenses: [GPL-*]\n")
    assert main(["scan", "-q", "--home", str(home), "--policy", str(policy),
                 "-o", str(tmp_path / "bom.json"), "--html", str(html)]) == 0
    text = html.read_text()
    assert text.startswith("<!doctype html>")
    assert "license-denied" in text and "gpl-skill" in text
    assert 'class="sev sev-critical"' in text
    assert "No license found" in text  # category chart includes unlicensed components
    # Same output through the report subcommand, and untrusted strings are escaped.
    bom = json.loads((tmp_path / "bom.json").read_text())
    bom["components"][0]["name"] = "<script>alert(1)</script>"
    (tmp_path / "evil.json").write_text(json.dumps(bom))
    assert main(["report", str(tmp_path / "evil.json"), "-o", str(html), "--title", "T"]) == 0
    text = html.read_text()
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;alert(1)" in text
    assert "<title>T</title>" in text


def test_report_on_example_bom(tmp_path):
    out = tmp_path / "r.html"
    assert main(["report", str(ROOT / "examples/skill-bom/acme-2026-10.json"), "-o", str(out)]) == 0
    text = out.read_text()
    assert "Skill license audit — ACME AG" in text
    assert "entitlement-insufficient" in text


def test_merge_hosts(tmp_path, capsys):
    # Machine A: "shared" skill with no license evidence, plus "only-a".
    a = tmp_path / "a"
    skill(a / ".claude/skills/shared", "shared")
    skill(a / ".claude/skills/only-a", "only-a", "license: MIT\n")
    # Machine B: the same "shared" content inside a project whose LICENSE is MIT.
    b = tmp_path / "b"
    write(b / "proj/LICENSE", MIT)
    skill(b / "proj/.claude/skills/shared", "shared")
    for name, home, extra in (("a", a, []), ("b", tmp_path / "empty", ["--project", str(b / "proj")])):
        assert main(["scan", "-q", "--home", str(home), "--host-id", f"host-{name}", "--organization", "ACME",
                     "-o", str(tmp_path / f"{name}.json"), *extra]) == 0
    out, html = tmp_path / "merged.json", tmp_path / "merged.html"
    assert main(["merge", "-q", str(tmp_path / "a.json"), str(tmp_path / "b.json"), str(tmp_path / "a.json"),
                 "-o", str(out), "--html", str(html)]) == 0
    bom = json.loads(out.read_text())
    schema = json.loads((ROOT / "schema/skill-bom.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(bom))

    shared = by_name(bom, "shared")
    assert sorted(i["host"] for i in shared["installations"]) == ["host-a", "host-b"]  # a.json twice: no dupes
    assert shared["license"]["expression"] == "MIT"  # stronger detection from host B wins
    assert rules(bom, "shared") == []  # host A's license-unknown is stale and dropped
    assert by_name(bom, "only-a")["installations"][0]["host"] == "host-a"
    assert bom["summary"]["hosts"] == 2 and bom["summary"]["components"] == 2
    assert [h["id"] for h in bom["metadata"]["scope"]["hosts"]] == ["host-a", "host-b"]
    assert bom["metadata"]["scope"]["organization"] == "ACME"
    assert len(bom["metadata"]["mergedFrom"]) == 3
    assert "2 hosts" in html.read_text()


def test_merge_warns_on_different_policies(tmp_path, capsys):
    skill(tmp_path / "r/s", "s")
    for name, policy in (("p1", "id: one\n"), ("p2", "id: two\n")):
        pol = write(tmp_path / f"{name}.yaml", policy)
        main(["scan", "-q", "--no-home", "--root", str(tmp_path / "r"), "--policy", str(pol),
              "-o", str(tmp_path / f"{name}.json")])
    capsys.readouterr()
    assert main(["merge", "-q", str(tmp_path / "p1.json"), str(tmp_path / "p2.json"),
                 "-o", str(tmp_path / "m.json")]) == 0
    assert "different policies" in capsys.readouterr().err
    assert "policy" not in json.loads((tmp_path / "m.json").read_text())["metadata"]
