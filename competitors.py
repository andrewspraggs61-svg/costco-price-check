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


def diagnose(term: str, stores: dict[str, dict]) -> dict:
    """
    Per-chain health check: run each lookup and report count or error, so we can
    tell (e.g. from a cloud host) which chains work from the server's IP.
    """
    def sid(chain):
        return (stores.get(chain) or {}).get("store_id")

    checks = {
        "Woolworths": (wlw.search, (term, 3)),
        "New World": (fs.search, ("New World", term, sid("New World"), 3)),
        "PAK'nSAVE": (fs.search, ("PAK'nSAVE", term, sid("PAK'nSAVE"), 3)),
    }
    out = {}
    for chain, (fn, args) in checks.items():
        try:
            products = fn(*args)
            out[chain] = {"ok": True, "count": len(products)}
        except Exception as e:
            out[chain] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    return out


def search_all(term: str, stores: dict[str, dict], limit_per_store: int = 4) -> list[Candidate]:
    """
    Query every chain and pool results.

    `stores` is the per-chain selection from stores.nearest_by_chain(), e.g.
    {"PAK'nSAVE": {"store_id": "<guid>"}, ...}. Foodstuffs needs the store id
    (franchise pricing); Woolworths ignores it (uniform national pricing).
    """
    from concurrent.futures import ThreadPoolExecutor

    def sid(chain: str):
        sel = stores.get(chain) or {}
        return sel.get("store_id")

    # Run all three chains concurrently so total latency is the slowest single
    # chain, not the sum -- important when one chain (e.g. Woolworths from an
    # overseas host) is slow to fail.
    jobs = [
        (wlw.search, (term, limit_per_store)),
        (fs.search, ("New World", term, sid("New World"), limit_per_store)),
        (fs.search, ("PAK'nSAVE", term, sid("PAK'nSAVE"), limit_per_store)),
    ]
    pooled: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(lambda job: _safe(job[0], *job[1]), jobs):
            pooled += result
    return pooled
