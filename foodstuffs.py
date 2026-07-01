"""
Foodstuffs (New World + PAK'nSAVE) live client.

Both banners run the identical stack, differing only by domain, so one module
serves both. Reverse-engineered from the sites' own JS (verified live):

  1. Anonymous token:   POST {web}/api/user/get-current-user  -> {access_token, ...}
  2. Store list:        GET  {api}/store                      -> stores w/ id + lat/long
  3. Product search:    POST {api}/search/paginated/products  (Bearer token)

The search endpoint only accepts sortOrder PRICE_ASC / PRICE_DESC; relevance is
handled by Algolia's text match on the query, and we re-rank by unit price
downstream anyway. Prices come back in **cents**.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

BANNERS = {
    "New World": {
        "web": "https://www.newworld.co.nz",
        "api": "https://api-prod.newworld.co.nz/v1/edge",
    },
    "PAK'nSAVE": {
        "web": "https://www.paknsave.co.nz",
        "api": "https://api-prod.paknsave.co.nz/v1/edge",
    },
}

# One session per process (keeps cookies); tokens cached with a conservative TTL
# so we don't hit the token endpoint on every search.
_session = requests.Session()
_session.headers.update({"User-Agent": _UA, "Accept": "application/json"})
_TOKEN_TTL = 600  # seconds
_token_cache: dict[str, tuple[str, float]] = {}   # banner -> (token, fetched_at)
_store_cache: dict[str, tuple[list, float]] = {}  # banner -> (stores, fetched_at)
_STORE_TTL = 6 * 3600


@dataclass
class Product:
    store: str
    name: str
    size: str
    price: float  # dollars


def _join_name(brand: str | None, name: str | None) -> str:
    """Prefix brand, but avoid doubling it when name already starts with it."""
    name = (name or "").strip()
    brand = (brand or "").strip()
    if brand and not name.lower().startswith(brand.lower()):
        return f"{brand} {name}".strip()
    return name or brand


def _get_token(banner: str) -> str:
    cached = _token_cache.get(banner)
    if cached and (time.time() - cached[1]) < _TOKEN_TTL:
        return cached[0]
    web = BANNERS[banner]["web"]
    # Prime cookies via a normal page load, then ask the site route for a token.
    _session.get(f"{web}/shop/search?q=x", timeout=20)
    r = _session.post(f"{web}/api/user/get-current-user", json={}, timeout=20)
    r.raise_for_status()
    token = r.json()["access_token"]
    _token_cache[banner] = (token, time.time())
    return token


def list_stores(banner: str) -> list[dict]:
    """Return [{id, name, lat, lon, banner}] for a banner (cached)."""
    cached = _store_cache.get(banner)
    if cached and (time.time() - cached[1]) < _STORE_TTL:
        return cached[0]
    token = _get_token(banner)
    r = _session.get(f"{BANNERS[banner]['api']}/store",
                     headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    raw = data if isinstance(data, list) else data.get("stores", [])
    stores = [
        {
            "id": s["id"],
            "name": s.get("name", ""),
            "lat": s.get("latitude"),
            "lon": s.get("longitude"),
            "banner": banner,
        }
        for s in raw if s.get("id")
    ]
    _store_cache[banner] = (stores, time.time())
    return stores


def _default_store_id(banner: str) -> str | None:
    stores = list_stores(banner)
    return stores[0]["id"] if stores else None


def search(banner: str, term: str, store_id: str | None, limit: int = 5) -> list[Product]:
    """Search a banner for `term` at `store_id` (falls back to a default store)."""
    if not term:
        return []
    store_id = store_id or _default_store_id(banner)
    if not store_id:
        return []
    token = _get_token(banner)
    body = {
        "algoliaQuery": {
            "query": term,
            "facetFilters": [[f"stores:{store_id}"]],
        },
        "storeId": store_id,
        "hitsPerPage": limit,
        "page": 0,
        "sortOrder": "PRICE_ASC",
        "tobaccoQuery": False,
    }
    r = _session.post(f"{BANNERS[banner]['api']}/search/paginated/products",
                      json=body, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    out: list[Product] = []
    for p in r.json().get("products", [])[:limit]:
        price_cents = (p.get("singlePrice") or {}).get("price")
        if price_cents is None:
            continue
        out.append(Product(
            store=banner,
            name=_join_name(p.get("brand"), p.get("name")),
            size=p.get("displayName", ""),   # Foodstuffs puts pack size here
            price=price_cents / 100.0,
        ))
    return out
