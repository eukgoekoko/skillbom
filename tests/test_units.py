import pytest

from skillbom import spdx, textmatch
from skillbom.hashing import content_hash

MIT = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software ... THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND"""


def test_parse_dnf():
    assert spdx.parse("MIT OR (Apache-2.0 AND BSD-3-Clause)") == [
        frozenset({"MIT"}), frozenset({"Apache-2.0", "BSD-3-Clause"})]
    assert spdx.parse("(MIT OR ISC) AND Zlib") == [frozenset({"MIT", "Zlib"}), frozenset({"ISC", "Zlib"})]


def test_normalize():
    assert spdx.normalize("mit or apache-2.0") == "MIT OR Apache-2.0"
    assert spdx.normalize("GPL-3.0+") == "GPL-3.0-or-later"
    assert spdx.normalize("Apache 2.0") == "Apache-2.0"
    assert spdx.normalize("(MIT OR LicenseRef-x) AND Zlib") == "(MIT OR LicenseRef-x) AND Zlib"
    assert spdx.normalize("GPL-2.0-only WITH Classpath-exception-2.0") == "GPL-2.0-only WITH Classpath-exception-2.0"
    for bad in ("Proprietary. See LICENSE.txt", "MIT OR", "(MIT", "SEE LICENSE IN LICENSE"):
        assert spdx.normalize(bad) is None


def test_choice_grants():
    assert spdx.choice_grants(frozenset({"MIT"}), "commercialUse") is True
    assert spdx.choice_grants(frozenset({"CC-BY-NC-4.0"}), "commercialUse") is False
    assert spdx.choice_grants(frozenset({"MIT", "CC-BY-NC-4.0"}), "commercialUse") is False
    assert spdx.choice_grants(frozenset({"LicenseRef-x"}), "commercialUse") is None
    assert spdx.choice_grants(frozenset({"CC-BY-NC-ND-4.0"}), "compose") is False
    assert spdx.choice_grants(frozenset({"PolyForm-Noncommercial-1.0.0"}), "commercialUse") is False
    assert spdx.choice_grants(frozenset({"LicenseRef-commons-clause"}), "serviceUse") is False


@pytest.mark.parametrize("text,expected", [
    (MIT, "MIT"),
    ("Apache License\n Version 2.0, January 2004", "Apache-2.0"),
    ("GNU GENERAL PUBLIC LICENSE Version 3 ... or (at your option) any later version.", "GPL-3.0-or-later"),
    ("GNU AFFERO GENERAL PUBLIC LICENSE Version 3", "AGPL-3.0-only"),
    ("GNU LESSER GENERAL PUBLIC LICENSE Version 2.1", "LGPL-2.1-only"),
    ("Attribution-NonCommercial 4.0 International", "CC-BY-NC-4.0"),
    ("(c) 2026 ACME. All rights reserved.", spdx.PROPRIETARY),
    ("PolyForm Noncommercial License 1.0.0\n<https://polyformproject.org/...>", "PolyForm-Noncommercial-1.0.0"),
    ("Elastic License 2.0 (ELv2)", "Elastic-2.0"),
    ("Business Source License 1.1 ... Additional Use Grant", "BUSL-1.1"),
    ("Functional Source License, Version 1.1, MIT Future License", "FSL-1.1-MIT"),
    ('"Commons Clause" License Condition v1.0 ... Apache License Version 2.0', "Apache-2.0 AND LicenseRef-commons-clause"),
])
def test_identify(text, expected):
    assert textmatch.identify(text)[0] == expected


@pytest.mark.parametrize("value,expected", [
    ("BSD-3-Clause license", "BSD-3-Clause"),
    ("Apache-2.0 (see LICENSE)", "Apache-2.0"),
    ("GPLv3 license", "GPL-3.0-only"),
    ("GNU General Public License v3.0", "GPL-3.0-only"),
    ("The Universal Permissive License (UPL), Version 1.0", "UPL-1.0"),
    ("MIT + Commons Clause", "MIT AND LicenseRef-commons-clause"),
    ("PolyForm Noncommercial 1.0.0 (free for noncommercial use; see LICENSE)", "PolyForm-Noncommercial-1.0.0"),
    ("UNLICENSED", spdx.PROPRIETARY),
    ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
    ("Unknown", None),
    ("Community License", None),
])
def test_from_name(value, expected):
    assert spdx.from_name(value) == expected


@pytest.mark.parametrize("text,expected", [
    ("MIT License - see repository root LICENSE file", "MIT"),
    ("MIT License\n\nBan quyen (c) 2024 someone ...", "MIT"),
    ("# PolyForm Shield License 1.0.0", "PolyForm-Shield-1.0.0"),
    ("zlib License ... Altered source versions must be plainly marked as such", "Zlib"),
])
def test_identify_more(text, expected):
    assert textmatch.identify(text)[0] == expected


def test_identify_unknown():
    assert textmatch.identify("do whatever") is None
    assert textmatch.identify("Databricks License\nCopyright (2022) Databricks") is None


def test_content_hash(tmp_path):
    (tmp_path / "SKILL.md").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.txt").write_text("b")
    h = content_hash(tmp_path)
    # Excluded files don't change the hash; content and paths do.
    (tmp_path / "skill-license.yaml").write_text("x")
    (tmp_path / ".DS_Store").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("x")
    assert content_hash(tmp_path) == h
    (tmp_path / "sub" / "x.txt").write_text("c")
    assert content_hash(tmp_path) != h
    (tmp_path / "sub" / "x.txt").write_text("b")
    (tmp_path / "sub" / "x.txt").rename(tmp_path / "sub" / "y.txt")
    assert content_hash(tmp_path) != h
