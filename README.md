# Costco NZ Price Check

Scan a Costco shelf tag on your phone and see whether it's cheaper at
Woolworths, PAK'nSAVE or New World — ranked by **unit price**, not shelf price.

Mobile web page (no app install). Open the link, tap **Add to Home Screen**, and
it behaves like an app on both iPhone and Android.

## Run it locally

```bash
cd CostcoPriceCheck
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 on the computer, or
`http://<your-computer-ip>:5000` on a phone on the same wifi.

> OCR needs the **Tesseract binary** installed separately
> (https://github.com/UB-Mannheim/tesseract/wiki). Without it the app still runs
> — it just asks you to type the item instead of reading the tag.

## What works now vs. what's stubbed

| Piece | Status |
|-------|--------|
| Mobile page + camera capture + Add-to-Home-Screen | ✅ working |
| Geolocation → nearest store per chain | ✅ **live** — real store IDs + coords from Foodstuffs (206 NZ stores) |
| Unit-price normalisation + ranking | ✅ working, unit-tested logic |
| Competitor price lookup | ✅ **LIVE** — real Woolworths, PAK'nSAVE & New World prices |
| OCR tag parsing | ✅ calibrated on a real tag (item 1825098); **needs Tesseract binary installed to read photo pixels** |

## Live API notes
- **Woolworths** (`woolworths.py`): public `GET /api/v1/products`, cookie-primed session + `x-requested-with` header. Prices in dollars; includes `size.volumeSize` and their own cup price.
- **New World + PAK'nSAVE** (`foodstuffs.py`): identical Foodstuffs stack. Anonymous token via `POST {web}/api/user/get-current-user`, then `POST {api}/search/paginated/products` (Bearer). Prices in **cents**; `sortOrder` only allows `PRICE_ASC`/`PRICE_DESC`. Token + store list cached.

## Next steps
1. Install the **Tesseract binary** to enable reading the tag photo (parsing already calibrated).
2. Deploy free (Render / Fly.io free tier) so it's reachable at Costco on mobile data.
3. Optional: fuzzy text-similarity (`rapidfuzz`) to refine which competitor rows are genuinely equivalent.
4. Optional: handle mixed-basis rows (e.g. a 250mL ghee shows $/L next to $/100g butters).

## Layout
```
app.py           Flask routes (thin controller)
unit_price.py    size parsing + $/100g,$/L,$/unit ranking  (pure logic)
ocr.py           Tesseract read + Costco tag field parsing
competitors.py   per-chain price lookup (currently mock)
stores.py        geolocation → nearest branch per chain
templates/       index.html (camera page + results UI)
static/          app.js, styles.css, manifest.webmanifest
```
