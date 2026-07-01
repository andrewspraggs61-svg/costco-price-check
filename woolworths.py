"""
Woolworths NZ live client.

Public search API (verified live). Needs a primed cookie session and the
`x-requested-with: OnlineShopping.WebApp` header. Prices are in dollars, and the
response conveniently includes both the pack size (`size.volumeSize`) and
Woolworths' own unit price (`size.cupPrice` / `size.cupMeasure`).

Woolworths online pricing is largely uniform nationally, so unlike Foodstuffs we
don't select a specific branch here -- the default store context is fine.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({"User-Agent": _UA, "Accept": "application/json"})
_primed = False


@dataclass
class Product:
    store: str
    name: str
    size: str
    price: float


def _join_name(brand: str | None, name: str | None) -> str:
    """Prefix brand, but avoid doubling it when name already starts with it."""
    name = (name or "").strip()
    brand = (brand or "").strip()
    if brand and not name.lower().startswith(brand.lower()):
        return f"{brand} {name}".strip()
    return name or brand


def _prime():
    global _primed
    if not _primed:
        _session.get("https://www.woolworths.co.nz/", timeout=20)
        _primed = True


def search(term: str, limit: int = 5) -> list[Product]:
    if not term:
        return []
    _prime()
    r = _session.get(
        "https://www.woolworths.co.nz/api/v1/products",
        params={"target": "search", "search": term,
                "inStockProductsOnly": "false", "size": str(limit)},
        headers={"x-requested-with": "OnlineShopping.WebApp"},
        timeout=20,
    )
    r.raise_for_status()
    items = r.json().get("products", {}).get("items", [])
    out: list[Product] = []
    for it in items[:limit]:
        if it.get("type") != "Product":
            continue
        price = (it.get("price") or {}).get("salePrice")
        if price is None:
            continue
        size = (it.get("size") or {}).get("volumeSize") or ""
        out.append(Product("Woolworths", _join_name(it.get("brand"), it.get("name")), size, price))
    return out
