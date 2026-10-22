"""Identify a license from the text of a LICENSE-style file."""

from __future__ import annotations

import re

from skillbom.spdx import PROPRIETARY, from_name

# Checked in order; more specific texts first. Each entry: (id, all phrases must occur).
_FINGERPRINTS: list[tuple[str, tuple[str, ...]]] = [
    ("PolyForm-Noncommercial-1.0.0", ("polyform noncommercial license 1.0.0",)),
    ("PolyForm-Small-Business-1.0.0", ("polyform small business license 1.0.0",)),
    ("PolyForm-Shield-1.0.0", ("polyform shield license 1.0.0",)),
    ("PolyForm-Internal-Use-1.0.0", ("polyform internal use license 1.0.0",)),
    ("UPL-1.0", ("universal permissive license",)),
    ("BUSL-1.1", ("business source license 1.1",)),
    ("Elastic-2.0", ("elastic license 2.0",)),
    ("SSPL-1.0", ("server side public license", "version 1")),
    ("FSL-1.1-ALv2", ("functional source license, version 1.1", "alv2 future license")),
    ("FSL-1.1-MIT", ("functional source license, version 1.1", "mit future license")),
    ("MPL-2.0", ("mozilla public license", "2.0")),
    ("Apache-2.0", ("apache license", "version 2.0")),
    ("CC-BY-NC-ND-4.0", ("attribution-noncommercial-noderivatives 4.0 international",)),
    ("CC-BY-NC-SA-4.0", ("attribution-noncommercial-sharealike 4.0 international",)),
    ("CC-BY-NC-4.0", ("attribution-noncommercial 4.0 international",)),
    ("CC-BY-ND-4.0", ("attribution-noderivatives 4.0 international",)),
    ("CC-BY-SA-4.0", ("attribution-sharealike 4.0 international",)),
    ("CC-BY-4.0", ("attribution 4.0 international",)),
    ("CC0-1.0", ("cc0 1.0 universal",)),
    ("Unlicense", ("this is free and unencumbered software released into the public domain",)),
    ("MIT", ("permission is hereby granted, free of charge", 'the software is provided "as is"')),
    ("ISC", ("permission to use, copy, modify, and/or distribute this software for any purpose",)),
    ("Zlib", ("altered source versions must be plainly marked as such",)),
    ("BSD-3-Clause", ("redistribution and use in source and binary forms", "neither the name")),
    ("BSD-2-Clause", ("redistribution and use in source and binary forms",)),
]

_COMMONS_CLAUSE = '"commons clause" license condition'
_PROPRIETARY_HINTS = ("all rights reserved", "proprietary")


def _normalize(text: str) -> str:
    text = text.lower().replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", text)


_HEADING = 300  # characters that hold a license's title
_OPENING = 1500  # characters that may hold a GNU "or any later version" notice
# GNU licenses are told apart by their heading: the GPL-3.0 text itself mentions the
# "GNU Affero General Public License" (section 13), so phrase matching would misfire.
_GNU_HEADINGS = [
    ("AGPL-3.0", ("gnu affero general public license",)),
    ("LGPL-3.0", ("gnu lesser general public license", "version 3")),
    ("LGPL-2.1", ("gnu lesser general public license", "version 2.1")),
    ("GPL-3.0", ("gnu general public license", "version 3")),
    ("GPL-2.0", ("gnu general public license", "version 2")),
]


def _gnu_suffix(t: str) -> str:
    # Only a notice at the top says "or any later version"; the full license text contains
    # that phrase in its "How to Apply" appendix, which says nothing about this project.
    later = t.find("any later version", 0, _OPENING)
    appendix = t.find("how to apply these terms")
    return "-or-later" if later >= 0 and (appendix < 0 or later < appendix) else "-only"


def _title(text: str) -> str:
    return re.split(r"[\n.]| - | \u2014 |copyright|\(c\)", text.strip().lstrip("\ufeff# ").lower(), maxsplit=1)[0].strip()


def identify(text: str) -> tuple[str, float] | None:
    """(SPDX id, confidence) for a license text, or None if unrecognized."""
    t = _normalize(text[:200_000])
    if _COMMONS_CLAUSE in t:
        # Appended to a base license (usually Apache-2.0 or MIT); both apply.
        base = identify(t.replace(_COMMONS_CLAUSE, ""))
        if base and base[0] != PROPRIETARY:
            return f"{base[0]} AND LicenseRef-commons-clause", base[1]
        return "LicenseRef-commons-clause", 0.8
    heading = t[:_HEADING]
    # Each GNU license mentions its siblings further down; the one named first is the title.
    titled = [(heading.find(phrases[0]), rank, lid) for rank, (lid, phrases) in enumerate(_GNU_HEADINGS)
              if all(p in heading for p in phrases)]
    if titled:
        return min(titled)[2] + _gnu_suffix(t), 0.85
    # A recognized title line wins over phrases further down (an MIT file that mentions
    # Apache-licensed third-party code is still MIT).
    title = _title(text)
    if title and len(title) < 60 and (named := from_name(title)):
        confirmed = any(lid == named and all(p in t for p in phrases) for lid, phrases in _FINGERPRINTS)
        return named, 0.9 if confirmed else 0.6
    for lid, phrases in _FINGERPRINTS:
        if all(p in t for p in phrases):
            return lid, 0.9
    for lid, phrases in _GNU_HEADINGS:  # a GNU text that doesn't start with its heading
        if all(p in t for p in phrases):
            return lid + _gnu_suffix(t), 0.7
    if any(h in t for h in _PROPRIETARY_HINTS):
        return PROPRIETARY, 0.5
    return None
