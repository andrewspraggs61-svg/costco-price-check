"""
Unit-price normalisation and ranking.

This is the pure-logic heart of the tool: given a Costco item and a pool of
competitor candidates, parse each one's size/weight/count, normalise every price
to a common basis ($/100g, $/L, or $/unit), and sort ascending so "cheapest per
unit" is meaningful across mismatched pack sizes.

No network, no Flask, no OCR -- fully unit-testable on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# --- Basis kinds ------------------------------------------------------------
# We normalise to one of three bases depending on how the product is sold.
BASIS_WEIGHT = "per_100g"   # solids: rice, butter, cheese ...
BASIS_VOLUME = "per_litre"  # liquids: milk, oil, juice ...
BASIS_COUNT = "per_unit"    # countables: eggs, toilet rolls, tea bags ...


@dataclass
class Sized:
    """A parsed product with enough info to compute a unit price."""
    name: str
    price: float                      # shelf price in NZD
    store: str = "Costco"
    # Parsed size, filled in by parse_size():
    basis: Optional[str] = None       # one of BASIS_* above
    base_qty: Optional[float] = None  # quantity expressed in the basis unit
    unit_price: Optional[float] = None
    raw_size: str = ""                # original size text, for display/debug

    @property
    def unit_label(self) -> str:
        return {
            BASIS_WEIGHT: "$/100g",
            BASIS_VOLUME: "$/L",
            BASIS_COUNT: "$/unit",
        }.get(self.basis or "", "?")


# --- Size parsing -----------------------------------------------------------
# Matches things like: 500g, 1.5kg, 2x500g, 750ml, 1L, 12pack, 6ea, 24 pk
_MULTIPLIER = r"(?:(\d+(?:\.\d+)?)\s*[x×]\s*)?"        # optional "2x"
_NUMBER = r"(\d+(?:\.\d+)?)"
_UNIT_WEIGHT = r"(kg|g)"
_UNIT_VOLUME = r"(l|ml)"
_UNIT_COUNT = r"(pack|pk|ea|each|ct|count|rolls?|pieces?|bags?|eggs?|units?)"

_RE_WEIGHT = re.compile(_MULTIPLIER + _NUMBER + r"\s*" + _UNIT_WEIGHT, re.I)
_RE_VOLUME = re.compile(_MULTIPLIER + _NUMBER + r"\s*" + _UNIT_VOLUME, re.I)
_RE_COUNT = re.compile(_MULTIPLIER + _NUMBER + r"\s*" + _UNIT_COUNT, re.I)
# Bare "12 pack" where the number leads and the count word follows loosely:
_RE_COUNT_LOOSE = re.compile(_NUMBER + r"\s*(?:x\s*)?" + _UNIT_COUNT, re.I)


def parse_size(text: str) -> tuple[Optional[str], Optional[float]]:
    """
    Parse a size string into (basis, quantity-in-basis-units).

    Returns (None, None) when nothing usable is found -- the caller decides
    whether to drop the candidate or fall back to shelf-price comparison.

    Examples
    --------
    "2x500g" -> (BASIS_WEIGHT, 1000.0)   # grams, then priced per 100g
    "1.5kg"  -> (BASIS_WEIGHT, 1500.0)
    "1L"     -> (BASIS_VOLUME, 1.0)
    "750ml"  -> (BASIS_VOLUME, 0.75)
    "12pack" -> (BASIS_COUNT, 12.0)
    """
    if not text:
        return None, None

    m = _RE_WEIGHT.search(text)
    if m:
        mult = float(m.group(1)) if m.group(1) else 1.0
        qty = float(m.group(2))
        unit = m.group(3).lower()
        grams = qty * (1000.0 if unit == "kg" else 1.0) * mult
        return BASIS_WEIGHT, grams

    m = _RE_VOLUME.search(text)
    if m:
        mult = float(m.group(1)) if m.group(1) else 1.0
        qty = float(m.group(2))
        unit = m.group(3).lower()
        litres = qty * (1.0 if unit == "l" else 0.001) * mult
        return BASIS_VOLUME, litres

    m = _RE_COUNT.search(text) or _RE_COUNT_LOOSE.search(text)
    if m:
        groups = m.groups()
        # _RE_COUNT has an optional leading multiplier group; _RE_COUNT_LOOSE
        # does not. Normalise both to (mult, qty).
        if len(groups) == 3:
            mult = float(groups[0]) if groups[0] else 1.0
            qty = float(groups[1])
        else:
            mult = 1.0
            qty = float(groups[0])
        return BASIS_COUNT, qty * mult

    return None, None


def compute_unit_price(item: Sized) -> Sized:
    """Fill in basis / base_qty / unit_price on a Sized in place, and return it."""
    basis, qty = parse_size(item.raw_size or item.name)
    item.basis, item.base_qty = basis, qty
    if basis and qty and qty > 0:
        if basis == BASIS_WEIGHT:
            item.unit_price = item.price / qty * 100.0   # $/100g
        elif basis == BASIS_VOLUME:
            item.unit_price = item.price / qty            # $/L
        else:
            item.unit_price = item.price / qty            # $/unit
    else:
        item.unit_price = None
    return item


def rank(costco: Sized, candidates: list[Sized]) -> list[Sized]:
    """
    Rank the Costco item together with all competitor candidates by unit price,
    cheapest first. Candidates whose size couldn't be parsed (unit_price is
    None) are sorted to the end so they're still visible but never "win"
    silently on a number we don't actually have.

    Only items that share the Costco item's basis are directly comparable, so we
    keep the basis on each row and let the UI show the unit so a $/100g vs $/L
    mix is obvious rather than hidden.
    """
    everything = [compute_unit_price(costco)] + [compute_unit_price(c) for c in candidates]

    def sort_key(s: Sized):
        # (has-unit-price?, unit-price) -> None sinks to the bottom.
        return (0, s.unit_price) if s.unit_price is not None else (1, float("inf"))

    return sorted(everything, key=sort_key)
