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

import woolworths as wlw   # kept as a fallback; Woolworths now comes via grocer
import foodstuffs as fs
import grocer


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
        "Woolworths": (grocer.search, (term, grocer.WOOLWORTHS_NATIONAL_STORE_ID, "Woolworths", 3)),
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

    # Only query chains the user left enabled -- a chain is "on" if it's present
    # in `stores`. This lets the UI switch off a shop (e.g. Woolworths, which is
    # blocked from the cloud host) so it's never even attempted.
    all_jobs = {
        # Woolworths via grocer.nz open data (works from the cloud host, unlike
        # querying Woolworths directly).
        "Woolworths": (grocer.search,
                       (term, grocer.WOOLWORTHS_NATIONAL_STORE_ID, "Woolworths", limit_per_store)),
        "New World": (fs.search, ("New World", term, sid("New World"), limit_per_store)),
        "PAK'nSAVE": (fs.search, ("PAK'nSAVE", term, sid("PAK'nSAVE"), limit_per_store)),
    }
    jobs = [job for chain, job in all_jobs.items() if chain in stores]

    # Run enabled chains concurrently so total latency is the slowest single
    # chain, not the sum.
    pooled: list[Candidate] = []
    if not jobs:
        return pooled
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(lambda job: _safe(job[0], *job[1]), jobs):
            pooled += result
    return pooled
