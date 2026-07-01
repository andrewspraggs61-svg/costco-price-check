// Front-end logic: geolocation -> nearest stores, scan/type -> ranked results.

const state = {
  stores: {},        // per-chain selection sent to the backend
  coords: null,
};

const $ = (id) => document.getElementById(id);

// --- Store selection by location -------------------------------------------
async function detectStores() {
  const locationLine = $("locationLine");
  if (!("geolocation" in navigator)) {
    locationLine.textContent = "Location not available — using default stores.";
    return loadStores(null, null);
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      loadStores(state.coords.lat, state.coords.lon);
    },
    () => {
      locationLine.textContent = "Location off — using default stores. (Tap ‘Stores’ to change.)";
      loadStores(null, null);
    },
    { enableHighAccuracy: false, timeout: 8000 }
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
  ["Woolworths", "PAK'nSAVE", "New World"].forEach((chain) => {
    const row = document.createElement("div");
    row.className = "store-row";
    const label = document.createElement("span");
    label.textContent = chain + ": ";
    const sel = document.createElement("select");
    (data.all || [])
      .filter((s) => s.chain === chain)
      .forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.store_id;
        opt.textContent = s.name;
        if (nearest[chain] && nearest[chain].store_id === s.store_id) opt.selected = true;
        sel.appendChild(opt);
      });
    sel.addEventListener("change", () => {
      state.stores[chain] = { ...(state.stores[chain] || {}), store_id: sel.value };
    });
    row.append(label, sel);
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
  fd.append("stores", JSON.stringify(state.stores));

  // Don't hang forever if the server is slow/asleep — fail with a clear message.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await fetch("/api/scan", { method: "POST", body: fd, signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json();

    if (data.status === "needs_manual") {
      status.textContent = data.message;
      $("manualBox").open = true;
      if (data.ocr) {
        $("name").value = $("name").value || data.ocr.description || "";
        $("size").value = $("size").value || data.ocr.size || "";
        if (data.ocr.price) $("price").value = $("price").value || data.ocr.price;
      }
      return;
    }

    status.textContent = `Searched for “${data.search_term}”.`;
    renderResults(data.results);
  } catch (e) {
    clearTimeout(timer);
    status.textContent = e.name === "AbortError"
      ? "The server took too long to respond. Give it a moment to wake up, then try again."
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
