"""
Competitor price lookup -- LIVE.

Dispatches a core search term to all three chains and pools the top few results
per store. Woolworths goes through woolworths.py; New World and PAK'nSAVE share
foodstuffs.py. Every lookup is wrapped so one chain failing (network hiccup,
token expiry, API change) never takes down the whole comparison -- that chain
just contributes no rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import woolworths as wlw
import foodstuffs as fs


@dataclass
class Candidate:
    store: str
    name: str
    size: str
    price: float


def _safe(fn, *args) -> list[Candidate]:
    """Run a chain lookup; on any error return [] instead of raising."""
    try:
        products = fn(*args)
        return [Candidate(p.store, p.name, p.size, p.price) for p in products]
    except Exception as e:  # network/token/shape changes shouldn't be fatal
        print(f"[competitors] lookup failed for {fn.__module__}: {e!r}")
        return []


def search_all(term: str, stores: dict[str, dict], limit_per_store: int = 4) -> list[Candidate]:
    """
    Query every chain and pool results.

    `stores` is the per-chain selection from stores.nearest_by_chain(), e.g.
    {"PAK'nSAVE": {"store_id": "<guid>"}, ...}. Foodstuffs needs the store id
    (franchise pricing); Woolworths ignores it (uniform national pricing).
    """
    def sid(chain: str):
        sel = stores.get(chain) or {}
        return sel.get("store_id")

    pooled: list[Candidate] = []
    pooled += _safe(wlw.search, term, limit_per_store)
    pooled += _safe(fs.search, "New World", term, sid("New World"), limit_per_store)
    pooled += _safe(fs.search, "PAK'nSAVE", term, sid("PAK'nSAVE"), limit_per_store)
    return pooled
