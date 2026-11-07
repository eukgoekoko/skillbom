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
    assert "enabled" not in tool["installations"][0]  # settings.json is never read
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


def _npx_skills_home(tmp_path) -> Path:
    """A home as `npx skills` leaves it: copies in ~/.agents/skills, symlinks in ~/.claude/skills,
    and the lock file naming each skill's repository."""
    h = tmp_path / "home"
    shared = h / ".agents/skills"
    skill(shared / "grill", "grill")  # Claude Code and the shared dir
    skill(shared / "only-shared", "only-shared")  # installed only for agents that read ~/.agents
    skill(shared / "local-one", "local-one")
    (h / ".claude/skills").mkdir(parents=True)
    (h / ".claude/skills/grill").symlink_to(shared / "grill")
    write(h / ".agents/.skill-lock.json", json.dumps({"version": 3, "skills": {
        "grill": {"source": "acme/skills", "sourceType": "github",
                  "sourceUrl": "https://github.com/acme/skills.git", "skillPath": "skills/misc/grill/SKILL.md"},
        "Only Shared": {"source": "acme/only-shared", "sourceType": "github", "skillPath": "SKILL.md"},
        "local-one": {"source": "/tmp/x", "sourceType": "local", "skillPath": "SKILL.md"},
    }}))
    return h


def test_npx_skills_lock_source(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    bom = scan(tmp_path, "--home", str(_npx_skills_home(tmp_path)))

    grill = by_name(bom, "grill")
    assert grill["source"] == {"type": "git", "url": "https://github.com/acme/skills", "path": "skills/misc/grill"}
    # The symlink and its target have the same content: one component, both installations.
    assert sorted((i["platform"], i["path"]) for i in grill["installations"]) == [
        ("agents", "~/.agents/skills/grill"), ("claude-code", "~/.claude/skills/grill")]
    [f] = [f for f in bom["findings"] if f["components"] == [grill["bomRef"]]]
    assert f["rule"] == "license-unknown"
    assert "https://github.com/acme/skills (skills/misc/grill)" in f["message"]
    assert "skill-license.yaml" in f["remediation"]

    # Lock keys are matched by the installer's sanitized folder name; a root skill has no path.
    assert by_name(bom, "only-shared")["source"] == {"type": "git", "url": "https://github.com/acme/only-shared"}
    assert by_name(bom, "local-one")["source"] == {"type": "local"}
    assert "~/.agents" in bom["metadata"]["scope"]["hosts"][0]["roots"]


def test_npx_skills_lock_under_xdg_state(tmp_path, monkeypatch):
    h = _npx_skills_home(tmp_path)
    state = tmp_path / "state"
    (state / "skills").mkdir(parents=True)
    (h / ".agents/.skill-lock.json").rename(state / "skills/.skill-lock.json")
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    bom = scan(tmp_path, "--home", str(h))
    assert by_name(bom, "grill")["source"]["type"] == "git"


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


def test_parent_manifest_and_body_license(tmp_path):
    root = tmp_path / "repo"
    write(root / "LICENSE", "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n")
    # Accuracy run, S015/S061/S196: a plugin declaring MIT inside an AGPL repo; nearest declaration wins.
    plugin = root / "plugins/p"
    write(plugin / ".claude-plugin/plugin.json", json.dumps({"name": "p", "license": "MIT"}))
    skill(plugin / "skills/inner", "inner")
    # Accuracy run, S082/S121: the only evidence is a repo-root plugin manifest.
    root2 = tmp_path / "repo2"
    write(root2 / ".claude-plugin/plugin.json", json.dumps({"name": "q", "license": "MIT"}))
    skill(root2 / "skills/only-manifest", "only-manifest")
    # Accuracy run, S120: a "## License" section in the SKILL.md body.
    s = root2 / "skills/body"
    write(s / "SKILL.md", "---\nname: body\ndescription: d\n---\n\n# body\n\n## License\n\n"
                          "Apache License 2.0. See [LICENSE](../../LICENSE) for full terms.\n")
    bom = scan(tmp_path, "--no-home", "--root", str(root), "--root", str(root2))
    inner = by_name(bom, "inner")
    assert inner["license"]["expression"] == "MIT"
    assert inner["license"]["evidence"][0]["source"] == "parent-manifest"
    assert by_name(bom, "only-manifest")["license"]["expression"] == "MIT"
    body = by_name(bom, "body")["license"]
    assert body["expression"] == "Apache-2.0" and body["evidence"][0]["source"] == "skill-body"


def test_spec_examples_are_valid():
    """Every YAML example in docs/license-file.md validates against the schema."""
    import re
    import yaml
    schema = json.loads((ROOT / "schema/skill-license.schema.json").read_text())
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / "docs/license-file.md").read_text(), re.S)
    assert len(blocks) >= 2
    for block in blocks:
        errors = list(Draft202012Validator(schema).iter_errors(yaml.safe_load(block)))
        assert not errors, errors


def test_subscription_requires_duration():
    import yaml
    schema = json.loads((ROOT / "schema/skill-license.schema.json").read_text())
    doc = yaml.safe_load("""specVersion: "0.1"
subject: {kind: skill, id: a/b, version: 1.0.0}
license:
  expression: LicenseRef-x
  text: LICENSE
  offers: [{id: LicenseRef-x, scope: {licensee: team}, term: {type: subscription}, grants: {}}]
""")
    assert list(Draft202012Validator(schema).iter_errors(doc))


def test_bom_spec_example_is_valid():
    """The JSON example in docs/skill-bom.md validates, and its references resolve."""
    import re
    schema = json.loads((ROOT / "schema/skill-bom.schema.json").read_text())
    [block] = re.findall(r"```json\n(.*?)```", (ROOT / "docs/skill-bom.md").read_text(), re.S)
    bom = json.loads(block)
    assert not list(Draft202012Validator(schema).iter_errors(bom))
    refs = {c["bomRef"] for c in bom["components"]}
    assert all(set(f["components"]) <= refs for f in bom["findings"])


def _cyclonedx_validator():
    """The official CycloneDX 1.6 JSON schema (tests/fixtures/cyclonedx, Apache-2.0)."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    base = ROOT / "tests/fixtures/cyclonedx"
    docs = [json.loads((base / n).read_text()) for n in ("bom-1.6.schema.json", "spdx.schema.json", "jsf-0.82.schema.json")]
    registry = Registry().with_resources((d["$id"], Resource.from_contents(d)) for d in docs)
    return Draft7Validator(docs[0], registry=registry)


def test_cyclonedx_export(home, tmp_path):
    policy = write(tmp_path / "policy.yaml", "id: test\ndeniedLicenses: [GPL-*]\n")
    cdx_file = tmp_path / "bom.cdx.json"
    assert main(["scan", "-q", "--home", str(home), "--policy", str(policy), "--host-id", "laptop-1",
                 "-o", str(tmp_path / "bom.json"), "--cyclonedx", str(cdx_file)]) == 0
    cdx = json.loads(cdx_file.read_text())
    errors = sorted(_cyclonedx_validator().iter_errors(cdx), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]

    bom = json.loads((tmp_path / "bom.json").read_text())
    assert cdx["serialNumber"] == bom["serialNumber"] and cdx["specVersion"] == "1.6"
    assert len(cdx["components"]) == len(bom["components"])
    alpha = next(c for c in cdx["components"] if c["name"] == "alpha")
    assert alpha["licenses"] == [{"expression": "MIT"}]
    assert alpha["hashes"][0]["alg"] == "SHA-256"
    assert alpha["evidence"]["occurrences"][0]["location"] == "laptop-1:~/.claude/skills/alpha"
    props = {p["name"]: p["value"] for p in alpha["properties"]}
    assert props["skillbom:kind"] == "skill" and props["skillbom:license.source"] == "skill-frontmatter"
    beta = next(c for c in cdx["components"] if c["name"] == "beta")
    assert "licenses" not in beta  # NOASSERTION is omitted, not exported as a license
    texts = [a["text"] for a in cdx["annotations"]]
    assert any(t.startswith("[critical] license-denied:") for t in texts)
    refs = {c["bom-ref"] for c in cdx["components"]}
    assert all(set(a["subjects"]) <= refs for a in cdx["annotations"])
    assert all(d["ref"] in refs and set(d["dependsOn"]) <= refs for d in cdx["dependencies"])

    # The export subcommand produces the same document from the saved BOM.
    out = tmp_path / "again.cdx.json"
    assert main(["export", str(tmp_path / "bom.json"), "-o", str(out)]) == 0
    assert json.loads(out.read_text()) == cdx


def test_cyclonedx_export_of_sample_bom():
    from skillbom.cyclonedx import to_cyclonedx
    for name in ("examples/skill-bom/acme-2026-10.json", "docs/demo/skillbom.json"):
        cdx = to_cyclonedx(json.loads((ROOT / name).read_text()))
        assert not list(_cyclonedx_validator().iter_errors(cdx)), name


def _license_validator():
    return Draft202012Validator(json.loads((ROOT / "schema/skill-license.schema.json").read_text()))


def test_init_creates_valid_declared_license(tmp_path, capsys):
    import yaml
    import subprocess
    repo = tmp_path / "repo"
    write(repo / "LICENSE", MIT)
    s = skill(repo / "skills/hello", "hello", "version: 1.2.0\n")
    # init looks for inherited licenses up to the git root (outside git: only the folder itself).
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert main(["init", str(s), "--publisher", "Jane Doe", "--copy-license"]) == 0
    doc = yaml.safe_load((s / "skill-license.yaml").read_text())
    assert not list(_license_validator().iter_errors(doc))
    assert doc["subject"]["id"] == "jane-doe/hello" and doc["subject"]["version"] == "1.2.0"
    assert doc["license"] == {"expression": "MIT", "text": "LICENSE"}
    assert (s / "LICENSE").read_text() == MIT  # copied, so the text travels with the skill
    assert doc["subject"]["contentHash"]["value"] == content_hash(s)

    # The scanner now reads it as a declared license with a matching hash.
    bom = scan(tmp_path, "--no-home", "--root", str(repo))
    c = by_name(bom, "hello")
    assert c["license"]["status"] == "declared" and c["integrity"] == "match" and c["id"] == "jane-doe/hello"

    # Editing the skill breaks the hash; --update refreshes it and keeps the rest.
    (s / "SKILL.md").write_text((s / "SKILL.md").read_text() + "\nMore.\n")
    assert by_name(scan(tmp_path, "--no-home", "--root", str(repo)), "hello")["integrity"] == "modified"
    assert main(["init", str(s), "--update", "--version", "1.3.0"]) == 0
    doc2 = yaml.safe_load((s / "skill-license.yaml").read_text())
    assert doc2["subject"]["version"] == "1.3.0" and doc2["license"] == doc["license"]
    assert by_name(scan(tmp_path, "--no-home", "--root", str(repo)), "hello")["integrity"] == "match"


def test_init_refusals(tmp_path, capsys):
    s = skill(tmp_path / "s", "s")
    assert main(["init", str(s), "--publisher", "x"]) == 2  # no license anywhere
    assert "--license" in capsys.readouterr().err
    assert main(["init", str(s), "--publisher", "x", "--license", "Proprietary stuff"]) == 2
    assert main(["init", str(s), "--publisher", "x", "--license", "LicenseRef-team"]) == 2
    assert "offers" in capsys.readouterr().err
    assert main(["init", str(s), "--license", "MIT"]) == 2  # no publisher (no git remote)
    assert main(["init", str(s), "--update"]) == 2  # nothing to update
    assert main(["init", str(tmp_path / "missing-dir-is-not-a-skill")]) == 2
    assert main(["init", str(s), "--publisher", "x", "--license", "MIT", "--dry-run"]) == 0
    assert not (s / "skill-license.yaml").exists()  # dry run writes nothing
    assert main(["init", str(s), "--publisher", "x", "--license", "MIT"]) == 0
    assert main(["init", str(s), "--publisher", "x", "--license", "MIT"]) == 2  # won't overwrite
    assert "--update" in capsys.readouterr().err


def test_plugin_runs_without_installed_pyyaml():
    """The plugin's launcher needs only python3: PyYAML ships in vendor/ (no downloads)."""
    import subprocess
    import sys
    plugin = ROOT / "plugins/skillbom"
    launcher = (plugin / "scripts/skillbom").read_text()
    import re
    assert not re.search(r"\b(pip|pip3|uv|uvx|curl|wget)\b", launcher), "the launcher must not download anything"
    code = ("import sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; import yaml, skillbom.cli; "
            "assert 'vendor' in yaml.__file__; print(yaml.__file__)")
    out = subprocess.run([sys.executable, "-S", "-c", code, str(plugin / "src"), str(plugin / "vendor")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert subprocess.run([str(plugin / "scripts/skillbom"), "--version"], capture_output=True, text=True).stdout.startswith("skillbom ")


def test_npx_skills_project_lock_in_home(tmp_path, monkeypatch):
    """skills 1.7.4 run from the home directory: a project install. Copies land in
    ~/.agents/skills (no symlinks) and the sources go to ~/skills-lock.json (version 1),
    while ~/.agents/.skill-lock.json only lists global installs."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    h = tmp_path / "home"
    skill(h / ".agents/skills/grill", "grill")
    skill(h / ".agents/skills/finder", "finder")
    write(h / "skills-lock.json", json.dumps({"version": 1, "skills": {
        "grill": {"source": "acme/skills", "sourceType": "github",
                  "skillPath": "skills/productivity/grill/SKILL.md", "computedHash": "0" * 64}}}))
    write(h / ".agents/.skill-lock.json", json.dumps({"version": 3, "skills": {
        "finder": {"source": "acme/tools", "sourceType": "github",
                   "sourceUrl": "https://github.com/acme/tools.git", "skillPath": "skills/finder/SKILL.md"}}}))
    bom = scan(tmp_path, "--home", str(h))
    assert by_name(bom, "grill")["source"] == {
        "type": "git", "url": "https://github.com/acme/skills", "path": "skills/productivity/grill"}
    assert by_name(bom, "finder")["source"]["url"] == "https://github.com/acme/tools"


def test_npx_skills_project_install(tmp_path):
    """--project DIR reads DIR/skills-lock.json for DIR/.agents/skills and the project's
    agent folders."""
    proj = tmp_path / "proj"
    skill(proj / ".agents/skills/review", "review")
    (proj / ".claude/skills").mkdir(parents=True)
    (proj / ".claude/skills/review").symlink_to(proj / ".agents/skills/review")
    write(proj / "skills-lock.json", json.dumps({"version": 1, "skills": {
        "review": {"source": "acme/review", "sourceType": "github", "skillPath": "SKILL.md"}}}))
    bom = scan(tmp_path, "--no-home", "--project", str(proj))
    review = by_name(bom, "review")
    assert review["source"] == {"type": "git", "url": "https://github.com/acme/review"}
    assert sorted((i["platform"], i["installScope"]) for i in review["installations"]) == [
        ("agents", "project"), ("claude-code", "project")]
