// Front-end logic: geolocation -> nearest stores, scan/type -> ranked results.

const state = {
  stores: {},        // per-chain selection sent to the backend
  coords: null,
  // Which shops are switched on. Woolworths now works via grocer.nz open data,
  // so it's back on by default.
  enabled: { "Woolworths": true, "New World": true, "PAK'nSAVE": true },
};

const $ = (id) => document.getElementById(id);

// --- Store selection by location -------------------------------------------
async function detectStores() {
  const locationLine = $("locationLine");
  locationLine.style.cursor = "pointer";
  locationLine.title = "Tap to retry location";
  locationLine.onclick = detectStores;   // tap the line to re-request location

  if (!("geolocation" in navigator)) {
    locationLine.textContent = "Location not available — pick your stores below.";
    return loadStores(null, null);
  }
  locationLine.textContent = "Finding your nearest stores…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      loadStores(state.coords.lat, state.coords.lon);
    },
    (err) => {
      const denied = err && err.code === 1;
      locationLine.textContent = denied
        ? "📍 Location blocked — allow it in your browser settings, then tap here to retry. (Or pick your stores below.)"
        : "📍 Couldn't get location — tap here to retry, or pick your stores below.";
      loadStores(null, null);
    },
    // More forgiving: longer wait, and accept a recent cached fix.
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 }
  );
}

async function loadStores(lat, lon) {
  const url = lat != null ? `/api/stores?lat=${lat}&lon=${lon}` : "/api/stores";
  try {
    const res = await fetch(url);
    const data = await res.json();
    state.stores = data.nearest || {};
    renderStoreSelection(data);
  } catch (e) {
    $("locationLine").textContent = "Couldn't load stores.";
  }
}

function renderStoreSelection(data) {
  const nearest = data.nearest || {};
  const chains = Object.keys(nearest);
  if (chains.length) {
    $("locationLine").textContent =
      "Comparing against: " + chains.map((c) => nearest[c].name).join(", ");
  }
  const box = $("storeSelection");
  box.innerHTML = "";
  ["PAK'nSAVE", "New World", "Woolworths"].forEach((chain) => {
    const row = document.createElement("div");
    row.className = "store-row";

    // On/off toggle for this shop.
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = !!state.enabled[chain];
    toggle.addEventListener("change", () => { state.enabled[chain] = toggle.checked; });

    const label = document.createElement("label");
    label.textContent = chain;
    label.style.minWidth = "92px";

    const sel = document.createElement("select");
    (data.all || [])
      .filter((s) => s.chain === chain)
      .forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.store_id == null ? "" : s.store_id;
        opt.textContent = s.name;
        if (nearest[chain] && nearest[chain].store_id === s.store_id) opt.selected = true;
        sel.appendChild(opt);
      });
    sel.addEventListener("change", () => {
      state.stores[chain] = { ...(state.stores[chain] || {}), store_id: sel.value };
    });
    // Woolworths is national (one option) — no point showing a picker.
    if (chain === "Woolworths") sel.style.display = "none";

    row.append(toggle, label, sel);
    box.appendChild(row);
  });
}

// --- Scan / check ----------------------------------------------------------
let pendingPhoto = null;

$("photo").addEventListener("change", (e) => {
  pendingPhoto = e.target.files[0] || null;
  if (pendingPhoto) {
    $("status").textContent = `Photo ready: ${pendingPhoto.name}. Tap “Check prices”.`;
  }
});

$("checkBtn").addEventListener("click", async () => {
  const status = $("status");
  status.textContent = "Checking prices… (the first check after a quiet spell can take up to a minute to wake the server)";

  const fd = new FormData();
  if (pendingPhoto) fd.append("photo", pendingPhoto);
  if ($("name").value) fd.append("name", $("name").value);
  if ($("size").value) fd.append("size", $("size").value);
  if ($("price").value) fd.append("price", $("price").value);

  // Send only the shops that are switched on. A chain present in this object is
  // queried; omitted = skipped entirely.
  const payload = {};
  ["Woolworths", "New World", "PAK'nSAVE"].forEach((chain) => {
    if (state.enabled[chain]) payload[chain] = state.stores[chain] || {};
  });
  if (Object.keys(payload).length === 0) {
    status.textContent = "Turn on at least one shop to compare.";
    return;
  }
  fd.append("stores", JSON.stringify(payload));

  // Don't hang forever if the server is slow/asleep — fail with a clear message.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);

  try {
    const res = await fetch("/api/scan", { method: "POST", body: fd, signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json();

    // If a photo was scanned, always surface what OCR actually read, and drop it
    // into the editable fields so a bad read can be corrected before comparing.
    const rb = $("readback");
    if (data.ocr && data.ocr.raw_text) {
      const o = data.ocr;
      $("name").value = o.description || $("name").value;
      $("size").value = o.size || $("size").value;
      if (o.price != null) $("price").value = o.price;
      $("manualBox").open = true;
      rb.hidden = false;
      rb.textContent = `📖 Read from photo — name: “${o.description || "?"}”, size: ${o.size || "?"}, price: ${o.price != null ? "$" + o.price : "?"}. If any of that is wrong, fix it above and tap Check prices again.`;
    } else {
      rb.hidden = true;
    }

    if (data.status === "needs_manual") {
      status.textContent = data.message;
      return;
    }

    status.textContent = data.note
      ? data.note
      : `Searched for “${data.search_term}”. Showing closest matches by unit price.`;
    renderResults(data.results);
  } catch (e) {
    clearTimeout(timer);
    status.textContent = e.name === "AbortError"
      ? "Server was asleep — it's waking up now. Wait ~10s, then tap Check prices again (the second try is fast)."
      : "Something went wrong. Try again.";
  }
});

function renderResults(rows) {
  const wrap = $("resultRows");
  wrap.innerHTML = "";
  rows.forEach((r, i) => {
    const div = document.createElement("div");
    div.className = "result" + (r.is_costco ? " costco" : "");
    const unit = r.unit_price != null ? `${r.unit_price} ${r.unit_label}` : "size ?";
    div.innerHTML = `
      <span class="rank">${i + 1}</span>
      <span class="rname">${r.name} <em>${r.size || ""}</em></span>
      <span class="rprice">$${r.price.toFixed(2)}<br><small>${unit}</small></span>
      <span class="rstore">${r.store}</span>`;
    wrap.appendChild(div);
  });
  $("results").hidden = rows.length === 0;
}

// --- init ------------------------------------------------------------------
detectStores();
