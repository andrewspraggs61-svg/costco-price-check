"""
Costco NZ Price Comparison -- Flask app.

Serves the mobile web page and the two JSON endpoints it needs:
  GET  /api/stores?lat=&lon=   -> nearest branch per chain (for the current location)
  POST /api/scan               -> photo (or typed item) -> ranked comparison

Everything downstream (OCR, competitor lookup, ranking) lives in its own module
so this file stays a thin controller.
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

import stores as stores_mod
import ocr as ocr_mod
import competitors as comp_mod
from unit_price import Sized, rank

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stores")
def api_stores():
    """Nearest branch per chain for a given location; falls back to full list."""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"nearest": {}, "all": stores_mod.all_stores(),
                        "error": "missing or invalid lat/lon"}), 400

    return jsonify({
        "nearest": stores_mod.nearest_by_chain(lat, lon),
        "all": stores_mod.all_stores(),
    })


@app.route("/api/debug")
def api_debug():
    """Per-chain lookup health check (which supermarkets work from this host)."""
    term = request.args.get("term", "butter")
    # Use each chain's default store when none supplied.
    return jsonify(comp_mod.diagnose(term, {}))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    Turn a scanned/typed Costco item into a ranked comparison.

    Accepts multipart/form-data:
      - photo:       (optional) the shelf-tag image
      - name, size, price: (optional) manual entry / OCR corrections
      - stores:      (optional) JSON of the per-chain store selection
    """
    import json

    # 1. Figure out the Costco item -- from OCR, from manual fields, or both.
    name = (request.form.get("name") or "").strip()
    size = (request.form.get("size") or "").strip()
    price_raw = (request.form.get("price") or "").strip()

    tag = None
    photo = request.files.get("photo")
    if photo is not None:
        tag = ocr_mod.read_tag(photo.read())
        # Only use OCR values where the user didn't supply a manual override.
        name = name or tag.description
        size = size or tag.size
        if not price_raw and tag.price is not None:
            price_raw = str(tag.price)

    # If we still can't identify the item, tell the client to prompt for entry.
    try:
        price = float(price_raw)
    except ValueError:
        price = None

    if not name or price is None:
        return jsonify({
            "status": "needs_manual",
            "ocr": _tag_to_dict(tag),
            "message": "Couldn't read the tag confidently -- please confirm the item.",
        })

    # 2. Reduce to a core search term and look up competitors.
    term = ocr_mod.core_search_term(name)
    try:
        selected = json.loads(request.form.get("stores") or "{}")
    except json.JSONDecodeError:
        selected = {}

    candidates = comp_mod.search_all(term, selected)

    # 3. Rank Costco item against the pooled competitor candidates.
    costco = Sized(name=name, price=price, store="Costco", raw_size=size)
    comp_sized = [
        Sized(name=c.name, price=c.price, store=c.store, raw_size=c.size)
        for c in candidates
    ]
    ranked = rank(costco, comp_sized)

    return jsonify({
        "status": "ok",
        "search_term": term,
        "ocr": _tag_to_dict(tag),
        "results": [_sized_to_dict(s) for s in ranked],
    })


def _tag_to_dict(tag) -> dict | None:
    if tag is None:
        return None
    return {
        "description": tag.description, "size": tag.size,
        "price": tag.price, "item_no": tag.item_no,
        "confident": tag.confident, "raw_text": tag.raw_text,
    }


def _sized_to_dict(s: Sized) -> dict:
    return {
        "store": s.store, "name": s.name, "size": s.raw_size,
        "price": round(s.price, 2),
        "unit_price": round(s.unit_price, 3) if s.unit_price is not None else None,
        "unit_label": s.unit_label,
        "is_costco": s.store == "Costco",
    }


if __name__ == "__main__":
    # 0.0.0.0 so a phone on the same network can reach it during local testing.
    app.run(host="0.0.0.0", port=5000, debug=True)
