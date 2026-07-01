"""
OCR the Costco shelf tag.

Reads a photo of a Costco tag and extracts (description, size, price, item_no).
Uses Tesseract locally (free). If Tesseract isn't installed yet, the functions
degrade gracefully so the rest of the app still runs end-to-end -- run_ocr()
returns empty text and the /scan route falls back to manual entry.

Tuning this against a REAL Costco tag photo is the single most important
calibration step for the whole project; the regexes below are a first guess at
Costco NZ's tag layout and will almost certainly need adjustment once we see one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TagFields:
    description: str = ""
    size: str = ""
    price: Optional[float] = None
    item_no: str = ""          # Costco's internal item number -- stable, good cache key
    raw_text: str = ""
    confident: bool = False    # False -> UI should ask the user to confirm/correct
    # Bonus: Costco prints its own unit price on the tag ("Per 100 g 1.39").
    # Handy as a sanity-check against our computed unit price.
    printed_unit_price: Optional[float] = None
    printed_unit_basis: str = ""   # e.g. "100 g", "kg", "ea"


# --- Tesseract wrapper (optional dependency) --------------------------------
# The Windows installer doesn't add Tesseract to PATH by default, so look in the
# usual install locations and point pytesseract straight at the binary.
_DEFAULT_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _locate_tesseract():
    """Configure pytesseract's binary path; return True if a binary was found."""
    import os
    import shutil
    import pytesseract

    if shutil.which("tesseract"):        # already on PATH
        return True
    for p in _DEFAULT_TESSERACT_PATHS:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            return True
    return False


def run_ocr(image_bytes: bytes) -> str:
    """
    Return raw OCR text for an image. If pytesseract/Pillow or the Tesseract
    binary aren't available, return "" so callers fall back to manual entry
    rather than crashing.
    """
    try:
        import io
        from PIL import Image
        import pytesseract
    except Exception:
        return ""

    if not _locate_tesseract():
        return ""

    try:
        from PIL import ImageOps, ImageFilter
        img = Image.open(io.BytesIO(image_bytes)).convert("L")  # greyscale
        # Normalise resolution before OCR. A full phone photo (~12MP) makes
        # Tesseract take ~2 minutes on a small free host -- fatal. Downscale big
        # images (tag text stays legible at ~1800px) and upscale tiny ones so
        # characters are tall enough to read. This is the key latency fix.
        TARGET = 1800
        longest = max(img.size)
        if longest > TARGET or longest < 1200:
            factor = TARGET / longest
            img = img.resize((max(1, int(img.width * factor)),
                              max(1, int(img.height * factor))), Image.LANCZOS)
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.SHARPEN)
        # psm 6 = assume a single uniform block of text, which a shelf tag is.
        return pytesseract.image_to_string(img, config="--psm 6")
    except Exception:
        return ""


# --- Field extraction -------------------------------------------------------
# Calibrated against a real Costco NZ tag:
#     1825098
#     KIRKLAND SIGNATURE GRASS-FED SALTED BUTTER 1KG
#     Per 100 g   1.39
#     13.89
# Item number is a bare 6-7 digit number (NOT prefixed with "Item #"), distinct
# from the 12-13 digit barcode. The pack size is embedded in the description
# line; "Per 100 g" is a unit-price label, not a size, and must be skipped.
_RE_PRICE = re.compile(r"\$?\s*(\d{1,4}\.\d{2})\b")
_RE_ITEM_NO = re.compile(r"\b(\d{6,7})\b")   # bare Costco item number
_RE_SIZE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:[x×]\s*\d+(?:\.\d+)?\s*)?"
    r"(?:kg|g|l|ml|pack|pk|ct|ea|each|count|rolls?|pieces?))\b",
    re.I,
)
# Costco's own printed unit price, e.g. "Per 100 g 1.39" or "Per kg $13.90".
_RE_PRINTED_UNIT = re.compile(
    r"per\s*(\d+\s*(?:g|kg|ml|l)|ea|each|kg|g|l|ml)\s*\$?\s*(\d+\.\d{2})",
    re.I,
)


def parse_tag(raw_text: str) -> TagFields:
    """Extract structured fields from raw OCR text. Best-effort, never raises."""
    fields = TagFields(raw_text=raw_text)
    if not raw_text.strip():
        return fields

    # Costco's own printed unit price -- parse it first so we can exclude it
    # from the shelf-price candidates below.
    printed_unit_val = None
    mu = _RE_PRINTED_UNIT.search(raw_text)
    if mu:
        fields.printed_unit_basis = re.sub(r"\s+", " ", mu.group(1)).strip()
        fields.printed_unit_price = float(mu.group(2))
        printed_unit_val = fields.printed_unit_price

    # Shelf price: the largest plausible price, ignoring the printed unit price.
    prices = [float(p) for p in _RE_PRICE.findall(raw_text)]
    prices = [p for p in prices if p != printed_unit_val]
    if prices:
        fields.price = max(prices)
    elif printed_unit_val is not None and not prices:
        fields.price = printed_unit_val  # degenerate fallback

    m = _RE_ITEM_NO.search(raw_text)
    if m:
        fields.item_no = m.group(1)

    # Pack size: first size match that isn't the "Per 100 g" unit label.
    for m in _RE_SIZE.finditer(raw_text):
        preceding = raw_text[max(0, m.start() - 5):m.start()].lower()
        if "per" in preceding:
            continue
        fields.size = m.group(1).strip()
        break

    # Description: join the alpha-heavy lines (brand + product), skipping the
    # "Per ..." unit-price line and the bare item-number/price lines.
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    desc_lines = [
        ln for ln in lines
        if sum(c.isalpha() for c in ln) >= 4 and not ln.lower().startswith("per")
    ]
    if desc_lines:
        fields.description = " ".join(desc_lines).strip()

    # Confident only if we got the essentials: a name and a shelf price.
    fields.confident = bool(fields.description and fields.price is not None)
    return fields


def read_tag(image_bytes: bytes) -> TagFields:
    """Full pipeline: OCR the image, then parse fields out of the text."""
    return parse_tag(run_ocr(image_bytes))


# --- Search-term reduction --------------------------------------------------
# Drop brand tokens and pack sizes so the competitor search uses the core term,
# e.g. "KS BUTTER 2X500G" -> "butter".
_NOISE_TOKENS = {
    "ks", "kirkland", "signature", "costco", "value", "brand",
    "pack", "pk", "ct", "count", "ea", "each",
    # unit words left behind when a size like "1KG" is tokenised to "kg":
    "kg", "g", "ml", "l", "litre", "litres", "gram", "grams",
}


def core_search_term(description: str) -> str:
    """
    Strip brand/size noise down to a searchable core product term, e.g.
    "KIRKLAND SIGNATURE GRASS-FED SALTED BUTTER 1KG" -> "grass fed salted butter".

    Note on specificity: this keeps the descriptive words. That's good for a
    precise match but can return zero competitor hits for Costco-specific
    phrasing -- if a search comes back empty, the intended fallback is to retry
    with just the final noun ("butter"). See last_noun_fallback().
    """
    if not description:
        return ""
    tokens = re.findall(r"[A-Za-z]+", description.lower())
    keep = [t for t in tokens if t not in _NOISE_TOKENS and len(t) > 1]
    return " ".join(keep).strip()


def last_noun_fallback(term: str) -> str:
    """Broadest possible retry: just the last word of the core term."""
    parts = term.split()
    return parts[-1] if parts else ""
