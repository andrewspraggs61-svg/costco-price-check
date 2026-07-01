"""
Store selection by location.

The phone reports its GPS position; we pick the nearest branch of each chain so
PAK'nSAVE / New World franchise pricing reflects a store the user would actually
shop at. Store data (with real store IDs + coordinates) is fetched live from
each Foodstuffs banner. Woolworths NZ prices uniformly nationally, so it's a
single "online" entry rather than a per-branch pick.

If the live fetch fails (offline), we fall back to a tiny hardcoded seed list so
the app still functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import foodstuffs as fs

# Woolworths is national -- one entry, no branch selection needed.
WOOLWORTHS_NATIONAL = {"chain": "Woolworths", "name": "Woolworths (online)",
                       "store_id": None, "lat": None, "lon": None}


@dataclass
class Store:
    chain: str
    name: str
    store_id: str
    lat: float
    lon: float


# Offline fallback only -- the real lists come from foodstuffs.list_stores().
SEED_STORES: list[Store] = [
    Store("PAK'nSAVE", "PAK'nSAVE Riccarton", "pns-riccarton", -43.5305, 172.5876),
    Store("New World",  "New World Ilam",     "nw-ilam",       -43.5215, 172.5836),
    Store("PAK'nSAVE", "PAK'nSAVE Kilbirnie", "pns-kilbirnie", -41.3186, 174.7936),
    Store("New World",  "New World Willis",   "nw-willis",     -41.2884, 174.7745),
    Store("PAK'nSAVE", "PAK'nSAVE Mt Albert", "pns-mtalbert",  -36.8899, 174.7143),
    Store("New World",  "New World Victoria", "nw-victoria",   -36.8471, 174.7539),
]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _live_foodstuffs_stores() -> list[dict] | None:
    """All New World + PAK'nSAVE stores with coordinates, or None if unavailable."""
    try:
        stores = fs.list_stores("New World") + fs.list_stores("PAK'nSAVE")
        stores = [s for s in stores if s.get("lat") is not None and s.get("lon") is not None]
        return stores or None
    except Exception as e:
        print(f"[stores] live store fetch failed: {e!r}")
        return None


def nearest_by_chain(lat: float, lon: float) -> dict[str, dict]:
    """Closest branch per chain to (lat, lon). Woolworths is always national."""
    result: dict[str, dict] = {
        "Woolworths": {"name": WOOLWORTHS_NATIONAL["name"], "store_id": None, "distance_km": None},
    }

    live = _live_foodstuffs_stores()
    if live:
        for s in live:
            d = _haversine_km(lat, lon, s["lat"], s["lon"])
            cur = result.get(s["banner"])
            if cur is None or cur.get("distance_km") is None or d < cur["distance_km"]:
                result[s["banner"]] = {"name": s["name"], "store_id": s["id"],
                                       "distance_km": round(d, 1)}
    else:
        # Offline fallback: nearest seed branch per chain.
        for st in SEED_STORES:
            d = _haversine_km(lat, lon, st.lat, st.lon)
            cur = result.get(st.chain)
            if cur is None or cur.get("distance_km") is None or d < cur["distance_km"]:
                result[st.chain] = {"name": st.name, "store_id": st.store_id,
                                    "distance_km": round(d, 1)}
    return result


def all_stores() -> list[dict]:
    """Flat list for the manual-override dropdown (live, seed fallback)."""
    live = _live_foodstuffs_stores()
    out = [dict(WOOLWORTHS_NATIONAL)]
    if live:
        out += [{"chain": s["banner"], "name": s["name"], "store_id": s["id"]}
                for s in sorted(live, key=lambda s: (s["banner"], s["name"]))]
    else:
        out += [{"chain": s.chain, "name": s.name, "store_id": s.store_id}
                for s in SEED_STORES]
    return out
