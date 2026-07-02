"""
Prices via grocer.nz open data.

grocer.nz publishes NZ supermarket data as public files (they offer it for
third-party use). This lets us get Woolworths prices from grocer's CDN instead
of querying Woolworths directly -- which matters because Woolworths blocks our
cloud host's overseas IP. Bonus: grocer's catalogue is unified, so matches are
by real product, and it covers all the chains.

Files used:
  - base catalogue (products/stores/barcodes): base_v3.duckdb.br  (downloaded once)
  - per-store prices:  prices_per_store_v3/public_prices_<store_id>.parquet

Everything is cached on disk with a TTL so we don't refetch on every scan.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass

import requests

_BASE_URL = "https://assets-prod.grocer.nz/public/base_v3.duckdb.br"
_STORE_PRICE_URL = ("https://assets-prod.grocer.nz/public/"
                    "prices_per_store_v3/public_prices_{store_id}.parquet")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Woolworths prices are ~uniform nationally, so one representative store's price
# file stands in for "Woolworths". (Church Corner has broad coverage.)
WOOLWORTHS_NATIONAL_STORE_ID = 31

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "grocer_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)
_BASE_TTL = 24 * 3600
_STORE_TTL = 12 * 3600


@dataclass
class Product:
    store: str
    name: str
    size: str
    price: float


def _download(url: str, dest: str):
    r = requests.get(url, timeout=120, headers={"User-Agent": _UA})
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return r.content


def _base_db_path() -> str:
    """Path to the cached base catalogue DuckDB, downloading/refreshing as needed."""
    path = os.path.join(_CACHE_DIR, "base_v3.duckdb")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < _BASE_TTL:
        return path
    data = _download(_BASE_URL, path + ".tmp")
    # The CDN may hand back the file already decompressed, or brotli-compressed.
    # A real DuckDB file carries the "DUCK" magic near the start.
    if b"DUCK" not in data[:64]:
        import brotli
        data = brotli.decompress(data)
    with open(path, "wb") as f:
        f.write(data)
    try:
        os.remove(path + ".tmp")
    except OSError:
        pass
    return path


def _store_price_path(store_id: int) -> str:
    path = os.path.join(_CACHE_DIR, f"prices_{store_id}.parquet")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < _STORE_TTL:
        return path
    _download(_STORE_PRICE_URL.format(store_id=store_id), path)
    return path


def search(term: str, store_id: int = WOOLWORTHS_NATIONAL_STORE_ID,
           store_label: str = "Woolworths", limit: int = 6) -> list[Product]:
    """
    Find products at a grocer store matching `term`, cheapest first.

    Matches products whose name contains all the search words; if that's too
    strict and finds nothing, falls back to matching any word.
    """
    words = [w for w in re.findall(r"[a-z]+", term.lower()) if len(w) > 1]
    if not words:
        return []

    import duckdb
    base = _base_db_path()
    ppath = _store_price_path(store_id).replace("\\", "/")
    con = duckdb.connect(base, read_only=True)

    price_expr = ("COALESCE(pr.sale_price_cent, pr.online_price_cent, "
                  "pr.original_price_cent)")

    # Require every search word to appear in the product name -- precise matches
    # only. If nothing matches we return nothing (the app then asks for a more
    # specific name) rather than surfacing loosely-related junk.
    cond = " AND ".join(["lower(p.name) LIKE ?"] * len(words))
    q = f"""
        SELECT p.name, p.size, p.unit, {price_expr} AS cents
        FROM read_parquet('{ppath}') pr
        JOIN public_products p ON p.id = pr.product_id
        WHERE ({cond}) AND {price_expr} IS NOT NULL
        ORDER BY cents
        LIMIT ?
    """
    rows = con.execute(q, [f"%{w}%" for w in words] + [limit]).fetchall()

    out = []
    for name, size, unit, cents in rows:
        out.append(Product(store_label, name, (size or unit or ""), cents / 100.0))
    return out
