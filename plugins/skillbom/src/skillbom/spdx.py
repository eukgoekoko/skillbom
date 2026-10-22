"""SPDX license expressions and the SPDX -> grants mapping table."""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources

import yaml

NOASSERTION = "NOASSERTION"
PROPRIETARY = "LicenseRef-proprietary"
CUSTOM = "LicenseRef-custom"  # a license text exists but isn't a known license

_TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z0-9.+:-]+)")
_LICENSEREF = re.compile(r"^(DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+$")


@lru_cache
def _table() -> dict:
    text = resources.files("skillbom").joinpath("data/spdx-grants.yaml").read_text()
    return yaml.safe_load(text)


@lru_cache
def _ids() -> dict[str, str]:
    """Lowercased id or alias -> canonical SPDX id."""
    t = _table()
    ids = {k.lower(): k for k in [*t["licenses"], *t["unmapped"]]}
    ids.update({k.lower(): v for k, v in t["aliases"].items()})
    return ids


_CC_URL = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z-]+)/(\d\.\d)", re.I)


def from_name(value: str) -> str | None:
    """SPDX expression for a free-text license name ("BSD-3-Clause license", "GPLv3"), or None."""
    if m := _CC_URL.search(value):
        kind, version = m.group(2).lower(), m.group(3)
        return "CC0-1.0" if kind == "zero" else canonical_id(f"CC-{kind.upper()}-{version}")
    text = re.sub(r"\([^)]*\)", " ", value.lower())
    text = re.sub(r"^\s*the\s+|\s+licen[cs]e\b", " ", text)
    text = re.sub(r"\s+([,;])", r"\1", re.sub(r"\s+", " ", text)).strip(" .;:-")
    if not text:
        return None
    names = _table().get("names") or {}
    if text in names:
        return names[text]
    return normalize(text)


def canonical_id(token: str) -> str | None:
    if _LICENSEREF.match(token):
        return token
    return _ids().get(token.lower())


def grants_for(license_id: str) -> dict | None:
    """Grant entry ({grants, obligations, copyleft}) for an SPDX id, or None if unmapped."""
    return _table()["licenses"].get(license_id)


def _tokenize(expr: str) -> list[str]:
    tokens, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip():
                raise ValueError(f"unexpected character at {pos}: {expr!r}")
            break
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


class _Parser:
    """Parses an expression into disjunctive normal form: a list of choices,
    each choice being the set of license ids that must all be complied with."""

    def __init__(self, tokens: list[str]):
        self.tokens, self.i = tokens, 0
        self.canonical: list[str] = []

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        self.i += 1
        return tok

    def parse(self) -> list[frozenset[str]]:
        result = self.or_expr()
        if self.peek() is not None:
            raise ValueError(f"unexpected token {self.peek()!r}")
        return result

    def or_expr(self):
        choices = self.and_expr()
        while (self.peek() or "").upper() == "OR":
            self.take()
            self.canonical.append("OR")
            choices = choices + self.and_expr()
        return choices

    def and_expr(self):
        choices = self.atom()
        while (self.peek() or "").upper() == "AND":
            self.take()
            self.canonical.append("AND")
            right = self.atom()
            choices = [a | b for a in choices for b in right]
        return choices

    def atom(self):
        tok = self.take()
        if tok == "(":
            self.canonical.append("(")
            inner = self.or_expr()
            if self.take() != ")":
                raise ValueError("expected ')'")
            self.canonical.append(")")
            return inner
        cid = canonical_id(tok)
        if cid is None:
            raise ValueError(f"unknown license id {tok!r}")
        self.canonical.append(cid)
        if (self.peek() or "").upper() == "WITH":
            self.take()
            exception = self.take()
            self.canonical += ["WITH", exception]
        # Exceptions only add permissions, so the base id is what the grant checks use.
        return [frozenset([cid])]


def parse(expr: str) -> list[frozenset[str]]:
    """DNF choices for an SPDX expression. Raises ValueError if invalid."""
    return _Parser(_tokenize(expr)).parse()


def normalize(value: str) -> str | None:
    """Canonical SPDX expression for a declared value, or None if it isn't one."""
    value = value.strip()
    if not value:
        return None
    alias = canonical_id(value)
    if alias:
        return alias
    try:
        p = _Parser(_tokenize(value))
        p.parse()
    except ValueError:
        return None
    text = " ".join(p.canonical)
    return text.replace("( ", "(").replace(" )", ")")


def choices(expr: str) -> list[frozenset[str]]:
    if expr == NOASSERTION:
        return []
    return parse(expr)


def choice_grants(choice: frozenset[str], grant: str) -> bool | None:
    """Whether every license in a choice grants `grant` (truthy, not 'none').
    None when any license in the choice has no mapping (LicenseRef-, unmapped ids)."""
    for lid in choice:
        entry = grants_for(lid)
        if entry is None:
            return None
        value = entry["grants"].get(grant)
        if value in (False, None, "none"):
            return False
    return True


CATEGORIES = ["permissive", "copyleft", "source-available", "non-commercial",
              "proprietary", "custom", "other", "none"]


def category(expr: str) -> str:
    """Coarse license category, taking the most permissive choice the licensee has."""
    if expr == NOASSERTION:
        return "none"
    if expr == PROPRIETARY:
        return "proprietary"
    if CUSTOM in expr:
        return "custom"
    cats = set()
    for choice in choices(expr):
        entries = [grants_for(i) for i in choice]
        if any(e is None for e in entries):
            cats.add("other")
        elif not all(e["grants"]["commercialUse"] for e in entries):
            cats.add("non-commercial")
        elif not all(e["grants"]["serviceUse"] for e in entries):
            cats.add("source-available")
        elif any(e["copyleft"] != "none" for e in entries):
            cats.add("copyleft")
        else:
            cats.add("permissive")
    return next((c for c in CATEGORIES if c in cats), "other")
