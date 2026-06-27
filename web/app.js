// LawfulStay — static frontend.
// Force redeploy trigger for GitHub Actions #4.
// Loads jurisdictions.json + changelog.json and renders a searchable/filterable/
// sortable table, a "latest regulatory changes" panel, a detail modal, and flags
// recently-changed jurisdictions. Includes interactive autocomplete and a compliance wizard.

const FIELD_LABELS = {
  status: "Regulatory Status",
  license_required: "License/Registration Required",
  tax_registration_required: "Tax Registration Required",
  fees: "Fees",
  primary_residence_required: "Primary Residence Required",
  rental_day_cap: "Annual Rental Day Cap",
  occupancy_limit: "Occupancy Limit",
  tax_rate: "Tax Rate",
  zoning_restrictions: "Zoning Restrictions",
  min_stay: "Minimum Stay Requirement",
  density_rules: "Density/Spacing Rules",
  insurance_required: "Insurance Required",
  platform_obligations: "Platform Obligations",
  compliance_notes: "Compliance Notes",
  effective_date: "Effective Date / Last Updated",
  key_notes: "Key Notes",
  penalties: "Penalties",
  additional_context: "Additional Context",
  source: "Source",
};

const RECENT_DAYS = 21;
let view = "list";
const CONTINENT_ORDER = [
  "North America", "Central America & Caribbean", "South America",
  "Europe", "Africa", "Middle East", "Asia", "Oceania", "Other",
];
let ALL = [];
let BY_ID = {};
let sortKey = "city";
let sortDir = 1;

// Map zoom and pan state
let scale = 1;
let offsetX = 0;
let offsetY = 0;
let isPanning = false;
let startX = 0;
let startY = 0;
let lastMouseX = 0;
let lastMouseY = 0;
let dragMoved = false;
const dragThreshold = 5;

const $ = (id) => document.getElementById(id);

async function fetchJson(urls) {
  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) return res.json();
    } catch (_) { /* try next */ }
  }
  return null;
}

function daysSince(iso) {
  const d = Date.parse((iso || "") + "T00:00:00");
  if (Number.isNaN(d)) return Infinity;
  return (Date.now() - d) / 86400000;
}
const isRecent = (j) => daysSince(j.last_changed) <= RECENT_DAYS;

// When "city" is a level descriptor (State Level / Nationwide) rather than an
// actual place, show the real geography as the headline and the descriptor below.
function displayName(j) {
  const c = (j.city || "").trim();
  if (/^(state level|state|nationwide|national)$/i.test(c)) {
    return { name: j.state || j.country, sub: c };
  }
  // Avoid repeating the city in the subtitle (e.g. "Lagos / Lagos"); fall back to country.
  const st = (j.state || "").trim();
  const subName = st && st !== c ? `${st}, ${j.country}` : j.country;
  return { name: c, sub: subName };
}

function uniqueSorted(key) {
  return [...new Set(ALL.map((j) => j[key]).filter(Boolean))].sort();
}

function fillSelect(el, values) {
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = v;
    el.appendChild(opt);
  }
}

function updateCountrySelect() {
  const continent = $("continent").value;
  const countrySelect = $("country");
  const selectedCountry = countrySelect.value;
  
  countrySelect.innerHTML = '<option value="">All Countries</option>';
  const jurisdictions = continent 
    ? ALL.filter(j => j.continent === continent)
    : ALL;
  const countries = [...new Set(jurisdictions.map(j => j.country).filter(Boolean))].sort();
  
  fillSelect(countrySelect, countries);
  if (countries.includes(selectedCountry)) {
    countrySelect.value = selectedCountry;
  } else {
    countrySelect.value = "";
  }
}


function matches(j) {
  const q = $("search").value.trim().toLowerCase();
  const continent = $("continent").value;
  const status = $("status").value;
  const country = $("country").value;
  if (continent && j.continent !== continent) return false;
  if (status && j.status !== status) return false;
  if (country && j.country !== country) return false;
  if (q && !Object.values(j).join(" ").toLowerCase().includes(q)) return false;
  return true;
}

function render() {
  const filtered = ALL.filter(matches);
  renderStats(filtered);
  const isTree = view === "tree";
  const isMap = view === "map";
  $("table-container").hidden = isTree || isMap || filtered.length === 0;
  $("tree").hidden = !isTree || filtered.length === 0;
  $("map").hidden = !isMap;
  $("tree-hint").hidden = !isTree || filtered.length === 0;
  $("map-hint").hidden = !isMap;
  $("empty").hidden = ALL.length === 0 || filtered.length > 0 || isMap;
  if (isTree) {
    if (filtered.length > 0) renderTree(filtered);
  } else if (isMap) {
    renderMap();
  } else {
    if (filtered.length > 0) renderList(filtered);
  }
  updateKpiCardActiveStates();
}

function renderList(filtered) {
  const rows = $("rows");
  rows.innerHTML = "";
  const sorted = filtered.slice().sort((a, b) => {
    const av = (a[sortKey] || "").toString().toLowerCase();
    const bv = (b[sortKey] || "").toString().toLowerCase();
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });
  for (const j of sorted) {
    const tr = document.createElement("tr");
    if (isRecent(j)) tr.className = "recent";
    const tag = recentTag(j);
    const disp = displayName(j);
    tr.innerHTML = `
      <td><div class="j-head"><span class="j-name">${esc(disp.name)}</span>${tag}</div><div class="j-sub">${esc(disp.sub)}</div></td>
      <td>${esc(j.continent)}</td>
      <td><span class="badge ${esc(j.status)}">${esc(j.status)}</span></td>
      <td><div class="clip" title="${esc(j.license_required)}">${licDot(j.license_required)}${esc(j.license_required)}</div></td>
      <td><div class="clip" title="${esc(j.rental_day_cap)}">${esc(j.rental_day_cap)}</div></td>
      <td><div class="clip" title="${esc(j.tax_rate)}">${esc(j.tax_rate)}</div></td>
      <td class="col-updated">${esc(j.last_changed)}</td>`;
    tr.addEventListener("click", () => openModal(j));
    rows.appendChild(tr);
  }
}

// Derive a quick license indicator from the free-text license field.
function licClass(text) {
  const s = (text || "").trim().toLowerCase();
  if (!s || s === "unknown") return "unknown";
  if (s.startsWith("yes")) return "yes";
  if (s.startsWith("no")) return "no";
  if (s.includes("varies") || s.includes("development") || s.includes("pending") ||
      s.includes("proposed") || s.includes("scheme")) return "varies";
  if (s.includes("license") || s.includes("permit") || s.includes("registration") ||
      s.includes("required")) return "yes";
  return "unknown";
}
const LIC_LABEL = {
  yes: "License required", no: "No license required",
  varies: "License varies / pending", unknown: "License status unknown",
};
function licDot(text) {
  const c = licClass(text);
  return `<span class="lic-dot lic-${c}" title="${LIC_LABEL[c]}"></span>`;
}

function recentTag(j) {
  return isRecent(j)
    ? `<span class="recent-tag" data-date="Updated ${esc(j.last_changed)}">Updated</span>`
    : "";
}

const GENERIC_CITY = /^(state level|state|nationwide|national|eu-wide)$/i;

function leafFacts(j) {
  const parts = [];
  const add = (lbl, v) => {
    const s = (v == null ? "" : String(v)).trim();
    if (s && s.toLowerCase() !== "unknown") parts.push(`${lbl} ${esc(s)}`);
  };
  add("License:", j.license_required);
  add("Cap:", j.rental_day_cap);
  add("Tax:", j.tax_rate);
  return parts.join(" &middot; ");
}

function leafEl(j, national) {
  const div = document.createElement("div");
  div.className = "t-leaf" + (national ? " national" : "");
  const c = (j.city || "").trim();
  const label = national && GENERIC_CITY.test(c) ? "Nationwide" : c;
  const tag = recentTag(j);
  const facts = leafFacts(j);
  div.innerHTML =
    `<span class="badge ${esc(j.status)}">${esc(j.status)}</span>` +
    `<span class="t-body">` +
    `<span class="t-head"><span class="t-name">${esc(label)}</span>${tag}</span>` +
    (facts ? `<span class="t-facts">${facts}</span>` : "") +
    `</span>`;
  div.addEventListener("click", () => openModal(j));
  return div;
}

// Build a collapsible Country > State > City tree from the filtered set.
function renderTree(filtered) {
  const tree = $("tree");
  tree.innerHTML = "";
  if (!filtered.length) return;

  const byCountry = {};
  for (const j of filtered) (byCountry[j.country] = byCountry[j.country] || []).push(j);

  for (const country of Object.keys(byCountry).sort()) {
    const recs = byCountry[country];
    const cDet = document.createElement("details");
    cDet.className = "t-country";
    const cSum = document.createElement("summary");
    cSum.innerHTML = `<span>${esc(country)}</span><span class="tcount">${recs.length}</span>`;
    cDet.appendChild(cSum);

    const national = [];
    const byState = {};
    for (const j of recs) {
      const st = (j.state || "").trim();
      if (!st) national.push(j);
      else (byState[st] = byState[st] || []).push(j);
    }
    national.sort((a, b) => a.city.localeCompare(b.city)).forEach((j) => cDet.appendChild(leafEl(j, true)));

    for (const st of Object.keys(byState).sort()) {
      const items = byState[st].sort((a, b) => a.city.localeCompare(b.city));
      const sDet = document.createElement("details");
      sDet.className = "t-state";
      const sSum = document.createElement("summary");
      sSum.innerHTML = `<span>${esc(st)}</span><span class="tcount">${items.length}</span>`;
      sDet.appendChild(sSum);
      items.forEach((j) => sDet.appendChild(leafEl(j, false)));
      cDet.appendChild(sDet);
    }
    tree.appendChild(cDet);
  }
}

function setView(v) {
  view = v;
  $("view-list").classList.toggle("active", v === "list");
  $("view-tree").classList.toggle("active", v === "tree");
  $("view-map").classList.toggle("active", v === "map");
  render();
}

// ---- Map view (client-side SVG, equirectangular projection) ----
const GEO_ALIAS = {
  "United States": "USA", "Czechia": "Czech Republic",
  "Bahamas": "The Bahamas", "United Kingdom": "England",
  "Serbia": "Republic of Serbia", "North Macedonia": "Macedonia",
};
const GEO_TO_OUR = Object.fromEntries(Object.entries(GEO_ALIAS).map(([k, v]) => [v, k]));
const STATUS_SEVERITY = { Banned: 4, Restricted: 3, Pending: 2, Active: 1, None: 0 };
let MAP_BUILT = false;
const MAP_PATHS = {};

function projPoint(lon, lat) {
  return ((lon + 180) / 360 * 1000).toFixed(1) + "," + ((90 - lat) / 180 * 500).toFixed(1);
}
function ringToPath(r) { return "M" + r.map((c) => projPoint(c[0], c[1])).join("L") + "Z"; }
function geomToPath(g) {
  if (g.type === "Polygon") return g.coordinates.map(ringToPath).join("");
  if (g.type === "MultiPolygon") return g.coordinates.map((p) => p.map(ringToPath).join("")).join("");
  return "";
}
const geoToOur = (g) => GEO_TO_OUR[g] || g;
const ourToGeo = (c) => GEO_ALIAS[c] || c;

function updateMapTransform() {
  const viewport = $("map-viewport");
  if (viewport) {
    viewport.setAttribute("transform", `translate(${offsetX}, ${offsetY}) scale(${scale})`);
  }
}

function constrainOffsets() {
  if (scale <= 1) {
    scale = 1;
    offsetX = 0;
    offsetY = 0;
    return;
  }
  const minX = 1000 * (1 - scale) - 200;
  const maxX = 200;
  const minY = 420 * (1 - scale) - 100;
  const maxY = 100;
  
  offsetX = Math.min(Math.max(offsetX, minX), maxX);
  offsetY = Math.min(Math.max(offsetY, minY), maxY);
}

function zoomAt(factor, cx, cy) {
  const oldScale = scale;
  scale = Math.min(Math.max(scale * factor, 1), 8);
  if (scale === oldScale) return;
  
  offsetX = cx - (scale / oldScale) * (cx - offsetX);
  offsetY = cy - (scale / oldScale) * (cy - offsetY);
  
  constrainOffsets();
  updateMapTransform();
}

async function ensureMapSvg() {
  if (MAP_BUILT) return;
  const geo = await fetchJson(["world.json"]);
  if (!geo) { $("map-svg").innerHTML = "<p class='empty'>Map data unavailable.</p>"; return; }
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 1000 420");
  
  const viewport = document.createElementNS(NS, "g");
  viewport.id = "map-viewport";
  
  for (const f of geo.features) {
    if (f.properties.name === "Antarctica") continue;
    const d = geomToPath(f.geometry);
    if (!d) continue;
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    p.dataset.geo = f.properties.name;
    viewport.appendChild(p);
    (MAP_PATHS[f.properties.name] = MAP_PATHS[f.properties.name] || []).push(p);
  }
  svg.appendChild(viewport);
  
  svg.addEventListener("click", onMapClick);
  svg.addEventListener("mousemove", onMapHover);
  svg.addEventListener("mouseleave", () => {
    if (window.mapScrollTimeout) {
      clearTimeout(window.mapScrollTimeout);
      window.mapScrollTimeout = null;
    }
    if (!isPanning) {
      $("map-info").textContent = "Hover a country — click to drill in";
    }
  });
  
  // Drag-to-pan handlers
  svg.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    isPanning = true;
    startX = e.clientX;
    startY = e.clientY;
    lastMouseX = offsetX;
    lastMouseY = offsetY;
    dragMoved = false;
    svg.style.cursor = "grabbing";
    e.preventDefault();
  });

  svg.addEventListener("wheel", (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const cx = (mouseX / rect.width) * 1000;
      const cy = (mouseY / rect.height) * 420;
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      zoomAt(factor, cx, cy);
    } else {
      const info = $("map-info");
      if (info) {
        const isMac = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgent || navigator.platform || "");
        const keyName = isMac ? "⌘ (Cmd)" : "Ctrl";
        const oldText = info.innerHTML;
        
        if (!info.innerHTML.includes("scroll to zoom")) {
          info.innerHTML = `<span style="color: var(--brand); font-weight: bold;"><i class="fa-solid fa-circle-info"></i> Use ${keyName} + scroll to zoom the map</span>`;
          if (window.mapScrollTimeout) clearTimeout(window.mapScrollTimeout);
          window.mapScrollTimeout = setTimeout(() => {
            if (info.innerHTML.includes("scroll to zoom")) {
              info.innerHTML = oldText;
            }
          }, 1800);
        }
      }
    }
  }, { passive: false });

  $("map-svg").innerHTML = "";
  $("map-svg").appendChild(svg);
  MAP_BUILT = true;
  updateMapTransform();
}

// A country's color is its NATIONAL-level rule, not its strictest city — so a
// single city ban (e.g. Santa Monica) doesn't paint the whole US red.
function nationalStatusFor(ourCountry) {
  const recs = ALL.filter((j) => j.country === ourCountry);
  if (!recs.length) return null; // untracked
  const nat = recs.find(
    (j) => (j.state || "").trim() === "" && /nationwide|national|eu-wide/i.test(j.city || "")
  );
  return nat ? nat.status : "LOCAL"; // tracked, but regulated locally (no national law)
}

function onMapHover(e) {
  if (window.mapScrollTimeout) {
    clearTimeout(window.mapScrollTimeout);
    window.mapScrollTimeout = null;
  }
  const g = e.target.dataset && e.target.dataset.geo;
  const info = $("map-info");
  if (!g) { info.textContent = "Hover a country — click to drill in"; return; }
  const our = geoToOur(g);
  const recs = ALL.filter((j) => j.country === our);
  if (!recs.length) { info.innerHTML = `<b>${esc(g)}</b> — not yet tracked`; return; }
  const ns = nationalStatusFor(our);
  const frame = ns === "LOCAL" ? "no national STR law (local control)" : `national framework: ${esc(ns)}`;
  const n = recs.length;
  info.innerHTML = `<b>${esc(our)}</b> — ${frame} · ${n} jurisdiction${n > 1 ? "s" : ""} · click to explore`;
}

function onMapClick(e) {
  if (dragMoved) {
    dragMoved = false;
    return;
  }
  const g = e.target.dataset && e.target.dataset.geo;
  if (!g) return;
  const our = geoToOur(g);
  const matched = ALL.find((j) => j.country === our);
  if (!matched) return;
  
  $("continent").value = matched.continent;
  updateCountrySelect();
  $("country").value = our;
  
  setView("tree");
  const det = [...document.querySelectorAll("#tree details.t-country")]
    .find((d) => d.querySelector("summary span").textContent === our);
  if (det) { det.open = true; det.scrollIntoView({ block: "start" }); }
}

async function renderMap() {
  await ensureMapSvg();
  for (const [geoName, paths] of Object.entries(MAP_PATHS)) {
    const ns = nationalStatusFor(geoToOur(geoName));
    const cls =
      ns === null ? "mc-untracked" : ns === "LOCAL" ? "tracked mc-local" : `tracked mc-${ns}`;
    for (const p of paths) p.setAttribute("class", cls);
  }
}

function renderStats(filtered) {
  const byStatus = {};
  for (const j of filtered) byStatus[j.status] = (byStatus[j.status] || 0) + 1;
  const chips = [`<span class="chip"><i class="fa-solid fa-earth-americas"></i> <b>${filtered.length}</b> shown</span>`];
  for (const s of ["Banned", "Restricted", "Active", "Pending", "None"]) {
    if (byStatus[s]) chips.push(`<span class="chip"><span class="dot dot-${s.toLowerCase()}"></span> ${s}: <b>${byStatus[s]}</b></span>`);
  }
  $("stats").innerHTML = chips.join("");
}

// Coverage/admin entries (bulk adds, expansions, seed) are audit records, not
// regulatory news — keep them out of the "Latest changes" feed.
const ADMIN_ENTRY = /(^seed$|-add$|expansion$)/;

function renderLatest(changelog) {
  if (!changelog || !changelog.entries) return;
  const entries = changelog.entries
    .filter((e) => !ADMIN_ENTRY.test(e.jurisdiction_id || "") && e.summary)
    .slice(0, 6);
  if (!entries.length) return;
  $("latest-list").innerHTML = entries.map((e) => {
    const where = BY_ID[e.jurisdiction_id]
      ? `<a class="where" href="#" data-id="${esc(e.jurisdiction_id)}">${esc(e.jurisdiction_label)}</a>`
      : `<span class="where">${esc(e.jurisdiction_label)}</span>`;
    return `<li><span class="when"><i class="fa-regular fa-calendar-days"></i> ${esc(e.date)}</span>` +
      `<span class="lc-content">${where} <span class="what">&mdash; ${esc(e.summary)}</span></span></li>`;
  }).join("");
  $("latest-list").querySelectorAll("a.where").forEach((a) =>
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      const j = BY_ID[a.dataset.id];
      if (j) openModal(j);
    }));
  $("latest").hidden = false;
}

function updateWizardProgress(step) {
  const stepsList = [1, 2, 3, "result"];
  stepsList.forEach((s) => {
    const el = $(`prog-step-${s}`);
    if (el) el.classList.remove("active", "completed");
  });
  
  const idx = stepsList.indexOf(step);
  for (let i = 0; i <= idx; i++) {
    const s = stepsList[i];
    const el = $(`prog-step-${s}`);
    if (el) {
      if (i === idx) {
        el.classList.add("active");
      } else {
        el.classList.add("completed");
      }
    }
  }
}

async function handleAlertSubscribe(event, id, label) {
  event.preventDefault();
  const form = event.target;
  const emailInput = form.email;
  const submitBtn = form.querySelector("button[type='submit']");
  const successMsg = form.querySelector(".subscribe-success-msg");
  const errorMsg = form.querySelector(".subscribe-error-msg");
  
  successMsg.style.display = "none";
  errorMsg.style.display = "none";
  
  const payload = {
    jurisdiction_id: id,
    jurisdiction_label: label,
    email: emailInput.value,
    website: form.website.value
  };
  
  submitBtn.disabled = true;
  const originalText = submitBtn.textContent;
  submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
  
  try {
    const res = await fetch("/api/subscribe-alerts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    
    const result = await res.json();
    
    if (res.ok && result.ok) {
      successMsg.textContent = result.message || "Subscribed successfully!";
      successMsg.style.display = "block";
      form.reset();
      // Keep disabled to prevent duplicate clicks
    } else {
      errorMsg.textContent = result.error || "An error occurred. Please try again.";
      errorMsg.style.display = "block";
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  } catch (err) {
    errorMsg.textContent = "Unable to connect to server. Please try again later.";
    errorMsg.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  }
}
window.handleAlertSubscribe = handleAlertSubscribe;

function openModal(j) {
  const sections = [
    {
      title: "Overview & Registry",
      icon: "fa-circle-info",
      keys: ["status", "effective_date", "license_required", "fees", "source"]
    },
    {
      title: "Operational Rules",
      icon: "fa-sliders",
      keys: ["primary_residence_required", "rental_day_cap", "occupancy_limit", "min_stay", "insurance_required"]
    },
    {
      title: "Zoning & Density",
      icon: "fa-map-location-dot",
      keys: ["zoning_restrictions", "density_rules"]
    },
    {
      title: "Taxes & Platform Rules",
      icon: "fa-receipt",
      keys: ["tax_registration_required", "tax_rate", "platform_obligations"]
    },
    {
      title: "Compliance Notes & Penalties",
      icon: "fa-triangle-exclamation",
      keys: ["compliance_notes", "key_notes", "penalties", "additional_context"]
    }
  ];

  const htmlContent = sections.map(sec => {
    const itemsHtml = sec.keys
      .map(k => {
        const val = j[k];
        const label = FIELD_LABELS[k];
        return `<dt>${label}</dt><dd>${linkify(val)}</dd>`;
      })
      .join("");
    
    return `
      <div class="detail-section-card">
        <h3 class="detail-section-title"><i class="fa-solid ${sec.icon}"></i> ${sec.title}</h3>
        <dl class="field-grid">${itemsHtml}</dl>
      </div>
    `;
  }).join("");

  const rt = recentTag(j);
  const recent = rt ? " " + rt : "";
  const disp = displayName(j);
  const locParts = [...new Set([j.state !== disp.name ? j.state : null, j.country, j.continent].filter(Boolean))];
  
  const labelEsc = esc(`${j.city}, ${j.country}`);
  const idEsc = esc(j.id);
  const subscribeCardHtml = `
    <div class="subscribe-alerts-card">
      <h4><i class="fa-solid fa-bell"></i> Stay Updated</h4>
      <p>Subscribe to receive email alerts when regulations change in ${esc(disp.name)}.</p>
      <form id="subscribe-alerts-form" onsubmit="handleAlertSubscribe(event, '${idEsc}', '${labelEsc}')">
        <div style="display: none;" aria-hidden="true">
          <label for="subscribe-website">Website</label>
          <input type="text" id="subscribe-website" name="website" autocomplete="off" />
        </div>
        <div class="subscribe-input-group">
          <input type="email" name="email" required placeholder="Enter your email address" class="form-input" aria-label="Email address" />
          <button type="submit" class="btn btn-primary btn-sm">Subscribe</button>
        </div>
        <div class="subscribe-success-msg" style="display: none; color: var(--active);"></div>
        <div class="subscribe-error-msg" style="display: none; color: var(--banned);"></div>
      </form>
    </div>
  `;

  $("modal-body").innerHTML = `
    <h2>${esc(disp.name)}${recent}</h2>
    <p class="loc">${esc(locParts.join(" · "))}</p>
    <div style="margin: -0.5rem 0 0.5rem 0; font-size: 0.8rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; border-bottom: 1px dashed var(--border); padding-bottom: 0.5rem;">
      <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
        <a href="#" onclick="openFeedbackDialog('${idEsc}', '${labelEsc}'); return false;" style="color: var(--brand); font-weight: 600; text-decoration: underline;"><i class="fa-solid fa-pen-to-square"></i> Report correction</a>
        <span style="color: var(--border);">|</span>
        <a href="#" onclick="window.print(); return false;" style="color: var(--brand); font-weight: 600; text-decoration: underline;"><i class="fa-solid fa-print"></i> Print rules</a>
      </div>
      <div class="drawer-share-row" style="font-size: 0.75rem; display: flex; align-items: center; gap: 0.4rem; color: var(--muted);">
        <span><i class="fa-solid fa-share-nodes"></i> Share:</span>
        <a href="https://www.facebook.com/sharer/sharer.php?u=https://lawfulstay.com/" target="_blank" rel="noopener" aria-label="Share on Facebook" style="color: #1877f2; font-size: 0.9rem; display: inline-flex; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform='scale(1)'"><i class="fa-brands fa-facebook"></i></a>
        <a href="https://www.linkedin.com/sharing/share-offsite/?url=https://lawfulstay.com/" target="_blank" rel="noopener" aria-label="Share on LinkedIn" style="color: #0077b5; font-size: 0.95rem; display: inline-flex; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform='scale(1)'"><i class="fa-brands fa-linkedin"></i></a>
        <a href="https://twitter.com/intent/tweet?text=${encodeURIComponent('Check out global short-term rental regulations for ' + disp.name + ' on LawfulStay:')}&url=https://lawfulstay.com/" target="_blank" rel="noopener" aria-label="Share on X" style="color: var(--text); font-size: 0.9rem; display: inline-flex; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform='scale(1)'"><i class="fa-brands fa-x-twitter"></i></a>
      </div>
    </div>
    <div class="detail-sections-container" style="margin-top: 0.5rem;">
      ${subscribeCardHtml}
      ${htmlContent}
    </div>`;
  $("modal").hidden = false;
}

function esc(s) {
  return (s ?? "").toString().replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function linkify(s) {
  const t = (s ?? "—").toString();
  return /^https?:\/\//.test(t)
    ? `<a href="${esc(t)}" target="_blank" rel="noopener">${esc(t)} <i class="fa-solid fa-up-right-from-square" style="font-size: 0.8rem"></i></a>`
    : esc(t || "—");
}

// Autocomplete suggestions for search input
function showAutocomplete(query) {
  const suggestBox = $("city-search-autocomplete");
  if (!suggestBox) return;

  const matches = ALL.filter(j => 
    j.city.toLowerCase().includes(query) ||
    j.country.toLowerCase().includes(query) ||
    (j.state && j.state.toLowerCase().includes(query))
  ).slice(0, 5);

  if (matches.length === 0) {
    suggestBox.style.display = "none";
    return;
  }

  suggestBox.innerHTML = "";
  matches.forEach(j => {
    const item = document.createElement("div");
    item.className = "autocomplete-item";
    const disp = displayName(j);
    item.innerHTML = `
      <span class="autocomplete-item-name">${esc(disp.name)}</span>
      <span class="autocomplete-item-meta">${esc(disp.sub)}</span>
    `;
    item.addEventListener("click", () => {
      $("search").value = disp.name;
      suggestBox.style.display = "none";
      $("clear-search").style.display = "block";
      render();
    });
    suggestBox.appendChild(item);
  });

  suggestBox.style.display = "block";
}

// Setup Compliance Assistant Wizard
function setupWizard() {
  const citySelect = $("assistant-city-select");
  const next1 = $("wizard-next-1");
  const next2 = $("wizard-next-2");
  const submit = $("wizard-submit");
  const restart = $("wizard-restart");
  
  if (!citySelect) return;

  const cityInput = $("assistant-city-input");
  const cityClear = $("assistant-city-clear");
  const cityAutocomplete = $("assistant-autocomplete");

  const validCities = ALL.filter(j => !/^(state level|state|nationwide|national|eu-wide)$/i.test(j.city))
                        .sort((a, b) => a.city.localeCompare(b.city));

  function filterCitySuggestions() {
    const query = cityInput.value.toLowerCase().trim();
    cityAutocomplete.innerHTML = "";
    
    // Invalidate selection on input change until a recommendation is clicked
    citySelect.value = "";
    next1.disabled = true;
    cityClear.style.display = "none";
    
    if (!query) {
      cityAutocomplete.style.display = "none";
      return;
    }
    
    const matches = validCities.filter(j => 
      j.city.toLowerCase().includes(query) || 
      (j.state && j.state.toLowerCase().includes(query)) ||
      j.country.toLowerCase().includes(query)
    );
    
    if (matches.length === 0) {
      const emptyItem = document.createElement("div");
      emptyItem.className = "autocomplete-item";
      emptyItem.style.cursor = "default";
      emptyItem.innerHTML = `<span class="autocomplete-item-name">No cities found</span>` +
        `<span class="autocomplete-item-meta"><a href="#" style="color: var(--brand); font-weight: 600;" onclick="openRequestDialog(); return false;">Request to add location</a></span>`;
      cityAutocomplete.appendChild(emptyItem);
    } else {
      matches.slice(0, 8).forEach(j => {
        const item = document.createElement("div");
        item.className = "autocomplete-item";
        
        const name = esc(j.city);
        const meta = esc(`${j.state ? j.state + ', ' : ''}${j.country}`);
        
        item.innerHTML = `<span class="autocomplete-item-name">${name}</span>` +
                         `<span class="autocomplete-item-meta">${meta}</span>`;
                         
        item.addEventListener("click", () => {
          selectCity(j);
        });
        cityAutocomplete.appendChild(item);
      });
    }
    cityAutocomplete.style.display = "block";
  }

  function selectCity(j) {
    citySelect.value = j.id;
    cityInput.value = `${j.city}, ${j.state ? j.state + ', ' : ''}${j.country}`;
    cityAutocomplete.style.display = "none";
    cityClear.style.display = "inline-flex";
    next1.disabled = false;
  }

  function clearCitySelection() {
    citySelect.value = "";
    cityInput.value = "";
    cityClear.style.display = "none";
    cityAutocomplete.style.display = "none";
    next1.disabled = true;
  }

  cityInput.addEventListener("input", filterCitySuggestions);
  
  cityInput.addEventListener("focus", () => {
    if (cityInput.value && !citySelect.value) {
      filterCitySuggestions();
    }
  });

  cityClear.addEventListener("click", clearCitySelection);

  // Close autocomplete on click outside
  document.addEventListener("click", (e) => {
    if (!cityInput.contains(e.target) && !cityAutocomplete.contains(e.target)) {
      cityAutocomplete.style.display = "none";
    }
  });

  const hostedRadios = document.getElementsByName("wizard-hosted");
  hostedRadios.forEach(radio => {
    radio.addEventListener("change", () => {
      next2.disabled = false;
    });
  });

  const residenceRadios = document.getElementsByName("wizard-residence");
  residenceRadios.forEach(radio => {
    radio.addEventListener("change", () => {
      submit.disabled = false;
    });
  });

  next1.addEventListener("click", () => {
    $("wizard-step-1").style.display = "none";
    $("wizard-step-2").style.display = "block";
    updateWizardProgress(2);
  });

  $("wizard-prev-2").addEventListener("click", () => {
    $("wizard-step-2").style.display = "none";
    $("wizard-step-1").style.display = "block";
    updateWizardProgress(1);
  });

  next2.addEventListener("click", () => {
    $("wizard-step-2").style.display = "none";
    $("wizard-step-3").style.display = "block";
    updateWizardProgress(3);
  });

  $("wizard-prev-3").addEventListener("click", () => {
    $("wizard-step-3").style.display = "none";
    $("wizard-step-2").style.display = "block";
    updateWizardProgress(2);
  });

  submit.addEventListener("click", runAnalysis);
  restart.addEventListener("click", resetWizard);
}

function runAnalysis() {
  const cityId = $("assistant-city-select").value;
  const j = BY_ID[cityId];
  if (!j) return;

  const isHosted = document.querySelector('input[name="wizard-hosted"]:checked').value === "yes";
  const isPrimary = document.querySelector('input[name="wizard-residence"]:checked').value === "primary";

  $("wizard-step-3").style.display = "none";
  $("wizard-result").style.display = "block";
  updateWizardProgress("result");

  $("result-city-name").textContent = j.city;
  $("result-badge-container").innerHTML = `<span class="badge ${esc(j.status)}">${esc(j.status)}</span>`;

  let verdictText = "";
  let violations = "None";
  let statusClass = "success";
  let iconHTML = '<i class="fa-solid fa-circle-check"></i>';

  const hasLicense = (j.license_required || "").toLowerCase();
  const needsLicense = hasLicense && !hasLicense.includes("no") && !hasLicense.includes("unknown");
  
  const hasPrimaryReq = (j.primary_residence_required || "").toLowerCase();
  const needsPrimary = hasPrimaryReq && !hasPrimaryReq.includes("no") && !hasPrimaryReq.includes("varies");

  // Specific city evaluation override templates
  if (j.id.includes("new-york-city") || j.city === "New York City") {
    if (!isHosted) {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = "Unhosted short-term rentals under 30 days are strictly illegal in NYC. You cannot rent out the entire apartment.";
      violations = "Unhosted stay restriction violated.";
    } else if (!isPrimary) {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = "NYC only allows home-sharing inside your primary home. Investment/secondary home hosting is prohibited.";
      violations = "Primary residency rule violated.";
    } else {
      statusClass = "warning";
      iconHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
      verdictText = "Allowed but highly regulated. You must reside in the unit during stays, register with the Office of Special Enforcement (OSE), and host a max of 2 guests.";
    }
  } else if (j.id.includes("barcelona") || j.city === "Barcelona") {
    if (isHosted) {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = "Barcelona has banned renting out private rooms (hosted stays) for short stays.";
      violations = "Hosted private room rentals banned.";
    } else {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = "Tourist apartments require a HUT license. However, Barcelona has frozen all new licenses and plans to phase them all out by 2028.";
      violations = "No new licenses are being issued.";
    }
  } else if (j.id.includes("los-angeles") || j.city === "Los Angeles") {
    if (!isPrimary) {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = "LA's Home-Sharing Ordinance bans hosting in second homes or investment properties. It must be your primary residence.";
      violations = "Primary residency rule violated.";
    } else {
      statusClass = "warning";
      iconHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
      verdictText = "Allowed up to 120 nights per year. You must obtain a Home-Sharing permit and display it on your listing.";
    }
  } else {
    // Dynamic fallback evaluations
    if (j.status === "Banned") {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = `Short-term rentals are banned or highly restricted in this jurisdiction: ${j.compliance_notes || j.key_notes || "prohibited"}`;
      violations = "STR prohibited status.";
    } else if (needsPrimary && !isPrimary) {
      statusClass = "danger";
      iconHTML = '<i class="fa-solid fa-circle-xmark"></i>';
      verdictText = `This jurisdiction limits short-term renting to primary residences only. Since you selected a secondary property, this listing strategy is illegal.`;
      violations = "Primary residence ordinance violated.";
    } else if (j.status === "Restricted") {
      statusClass = "warning";
      iconHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
      verdictText = `Allowed with restrictions: ${j.compliance_notes || j.key_notes || "permit & operational rules apply."}`;
      if (needsLicense) violations = "License & permit registration required.";
    } else {
      statusClass = "success";
      verdictText = `Highly feasible! This city has a flexible stance on short-term rentals. Review local permits and tax registrations.`;
    }
  }

  // Populate Result Card
  const verdictBox = $("result-verdict-box");
  verdictBox.className = `verdict-box ${statusClass}`;
  
  const iconBox = $("result-status-icon");
  iconBox.className = `status-icon-box ${statusClass}`;
  iconBox.innerHTML = iconHTML;

  $("result-verdict-text").textContent = verdictText;
  $("result-violations").textContent = violations;
  
  $("result-permit-status").textContent = j.license_required || "Not Required";
  $("result-cap-status").textContent = j.rental_day_cap || "No Cap";

  const portalBtn = $("result-portal-link");
  if (j.source && j.source.startsWith("http")) {
    portalBtn.setAttribute("href", j.source);
    portalBtn.style.display = "inline-flex";
  } else {
    portalBtn.setAttribute("href", "#");
    portalBtn.style.display = "none";
  }
}

function resetWizard() {
  $("assistant-city-select").value = "";
  if ($("assistant-city-input")) $("assistant-city-input").value = "";
  if ($("assistant-city-clear")) $("assistant-city-clear").style.display = "none";
  
  const hostedRadios = document.getElementsByName("wizard-hosted");
  hostedRadios.forEach(radio => radio.checked = false);
  
  const residenceRadios = document.getElementsByName("wizard-residence");
  residenceRadios.forEach(radio => radio.checked = false);
  
  $("wizard-next-1").disabled = true;
  $("wizard-next-2").disabled = true;
  $("wizard-submit").disabled = true;
  
  $("wizard-result").style.display = "none";
  $("wizard-step-2").style.display = "none";
  $("wizard-step-3").style.display = "none";
  $("wizard-step-1").style.display = "block";
  updateWizardProgress(1);
}

function setupSubscribeDialog() {
  const dialogInput = $("subscribe-search-input");
  const dialogSuggestions = $("subscribe-suggestions");
  const dialogClear = $("subscribe-search-clear");
  const dialogSelectedId = $("subscribe-selected-id");
  const dialogSelectedLabel = $("subscribe-selected-label");
  const submitBtn = $("subscribe-dialog-submit");

  if (!dialogInput) return;

  function filterSuggestions() {
    const query = dialogInput.value.toLowerCase().trim();
    dialogSuggestions.innerHTML = "";
    
    // Invalidate selection on input change
    dialogSelectedId.value = "";
    dialogSelectedLabel.value = "";
    submitBtn.disabled = true;
    dialogClear.style.display = "none";
    
    if (!query) {
      dialogSuggestions.style.display = "none";
      return;
    }
    
    const matches = ALL.filter(j => 
      j.city.toLowerCase().includes(query) || 
      (j.state && j.state.toLowerCase().includes(query)) ||
      j.country.toLowerCase().includes(query)
    );
    
    if (matches.length === 0) {
      const emptyItem = document.createElement("div");
      emptyItem.className = "autocomplete-item";
      emptyItem.style.cursor = "default";
      emptyItem.innerHTML = `<span class="autocomplete-item-name">No locations found</span>` +
        `<span class="autocomplete-item-meta"><a href="#" style="color: var(--brand); font-weight: 600;" onclick="closeSubscribeDialog(); openRequestDialog(); return false;">Request to add location</a></span>`;
      dialogSuggestions.appendChild(emptyItem);
    } else {
      matches.slice(0, 8).forEach(j => {
        const item = document.createElement("div");
        item.className = "autocomplete-item";
        
        const disp = displayName(j);
        const name = esc(disp.name);
        const meta = esc(disp.sub);
        
        item.innerHTML = `<span class="autocomplete-item-name">${name}</span>` +
                         `<span class="autocomplete-item-meta">${meta}</span>`;
                         
        item.addEventListener("click", () => {
          selectJurisdiction(j);
        });
        dialogSuggestions.appendChild(item);
      });
    }
    dialogSuggestions.style.display = "block";
  }

  function selectJurisdiction(j) {
    const disp = displayName(j);
    dialogSelectedId.value = j.id;
    dialogSelectedLabel.value = `${disp.name}, ${j.country}`;
    dialogInput.value = `${disp.name}, ${j.state ? j.state + ', ' : ''}${j.country}`;
    dialogSuggestions.style.display = "none";
    dialogClear.style.display = "inline-flex";
    submitBtn.disabled = false;
  }

  function clearSelection() {
    dialogSelectedId.value = "";
    dialogSelectedLabel.value = "";
    dialogInput.value = "";
    dialogClear.style.display = "none";
    dialogSuggestions.style.display = "none";
    submitBtn.disabled = true;
  }

  dialogInput.addEventListener("input", filterSuggestions);
  
  dialogInput.addEventListener("focus", () => {
    if (dialogInput.value && !dialogSelectedId.value) {
      filterSuggestions();
    }
  });

  dialogClear.addEventListener("click", clearSelection);

  // Close suggestions if clicked outside
  document.addEventListener("click", (e) => {
    if (!dialogInput.contains(e.target) && !dialogSuggestions.contains(e.target)) {
      dialogSuggestions.style.display = "none";
    }
  });
}

function openSubscribeDialog() {
  const dialog = document.getElementById("subscribe-dialog");
  if (dialog) {
    document.getElementById("subscribe-dialog-form").reset();
    document.getElementById("subscribe-selected-id").value = "";
    document.getElementById("subscribe-selected-label").value = "";
    document.getElementById("subscribe-search-clear").style.display = "none";
    document.getElementById("subscribe-suggestions").style.display = "none";
    document.querySelector("#subscribe-dialog .dialog-success-msg").style.display = "none";
    document.querySelector("#subscribe-dialog .dialog-error-msg").style.display = "none";
    const submitBtn = document.getElementById("subscribe-dialog-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "Subscribe";
    dialog.hidden = false;
  }
}

function closeSubscribeDialog() {
  const dialog = document.getElementById("subscribe-dialog");
  if (dialog) dialog.hidden = true;
}

async function handleDialogSubscribe(event) {
  event.preventDefault();
  const form = event.target;
  const emailInput = form.email;
  const jIdInput = form.jurisdiction_id;
  const jLabelInput = form.jurisdiction_label;
  const submitBtn = document.getElementById("subscribe-dialog-submit");
  const successMsg = form.querySelector(".dialog-success-msg");
  const errorMsg = form.querySelector(".dialog-error-msg");

  successMsg.style.display = "none";
  errorMsg.style.display = "none";

  if (!jIdInput.value || !jLabelInput.value) {
    errorMsg.textContent = "Please select a valid location from the suggestions list.";
    errorMsg.style.display = "block";
    return;
  }

  const payload = {
    jurisdiction_id: jIdInput.value,
    jurisdiction_label: jLabelInput.value,
    email: emailInput.value,
    website: form.website.value
  };

  submitBtn.disabled = true;
  const originalText = submitBtn.textContent;
  submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';

  try {
    const res = await fetch("/api/subscribe-alerts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const result = await res.json();

    if (res.ok && result.ok) {
      successMsg.textContent = result.message || "Successfully subscribed to alerts!";
      successMsg.style.display = "block";
      form.reset();
      document.getElementById("subscribe-search-clear").style.display = "none";
      setTimeout(() => {
        closeSubscribeDialog();
      }, 2500);
    } else {
      errorMsg.textContent = result.error || "An error occurred. Please try again.";
      errorMsg.style.display = "block";
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  } catch (err) {
    errorMsg.textContent = "Unable to connect to server. Please try again later.";
    errorMsg.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  }
}

window.openSubscribeDialog = openSubscribeDialog;
window.closeSubscribeDialog = closeSubscribeDialog;
window.handleDialogSubscribe = handleDialogSubscribe;

function wire() {
  $("continent").addEventListener("input", () => {
    updateCountrySelect();
    render();
  });
  
  ["search", "status", "country"].forEach((id) =>
    $(id).addEventListener("input", render));
  
  $("kpi-tracked").addEventListener("click", () => {
    ["search", "continent", "status", "country"].forEach((id) => ($(id).value = ""));
    $("clear-search").style.display = "none";
    updateCountrySelect();
    render();
  });

  $("kpi-monitored").addEventListener("click", () => {
    ["search", "continent", "status", "country"].forEach((id) => ($(id).value = ""));
    $("clear-search").style.display = "none";
    updateCountrySelect();
    render();
  });

  document.querySelectorAll(".kpi-info-trigger").forEach((trigger) => {
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const message = trigger.getAttribute("title") || "";
      if (message) {
        showToast(message);
      }
    });
  });

  $("kpi-bans").addEventListener("click", () => {
    const s = $("status");
    s.value = s.value === "Banned" ? "" : "Banned";
    render();
  });

  $("kpi-caps").addEventListener("click", () => {
    const s = $("status");
    s.value = s.value === "Restricted" ? "" : "Restricted";
    render();
  });

  $("kpi-allowed").addEventListener("click", () => {
    const s = $("status");
    s.value = s.value === "Active" ? "" : "Active";
    render();
  });
  
  $("reset").addEventListener("click", () => {
    ["search", "continent", "status", "country"].forEach((id) => ($(id).value = ""));
    $("clear-search").style.display = "none";
    updateCountrySelect();
    
    // Reset map zoom
    scale = 1;
    offsetX = 0;
    offsetY = 0;
    updateMapTransform();
    
    render();
  });

  
  // Custom search clear button
  const searchInput = $("search");
  const clearBtn = $("clear-search");
  
  if (searchInput && clearBtn) {
    searchInput.addEventListener("input", () => {
      const val = searchInput.value.trim();
      clearBtn.style.display = val.length > 0 ? "block" : "none";
      if (val.length > 0) {
        showAutocomplete(val.toLowerCase());
      } else {
        $("city-search-autocomplete").style.display = "none";
      }
    });

    clearBtn.addEventListener("click", () => {
      searchInput.value = "";
      clearBtn.style.display = "none";
      $("city-search-autocomplete").style.display = "none";
      render();
      searchInput.focus();
    });

    // Close autocomplete when clicking outside
    document.addEventListener("click", (e) => {
      const suggestBox = $("city-search-autocomplete");
      if (suggestBox && !searchInput.contains(e.target) && !suggestBox.contains(e.target)) {
        suggestBox.style.display = "none";
      }
    });
  }

  document.querySelectorAll("th[data-key]").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.key;
      sortDir = sortKey === k ? -sortDir : 1;
      sortKey = k;
      render();
    }));
  
  $("view-list").addEventListener("click", () => setView("list"));
  $("view-tree").addEventListener("click", () => setView("tree"));
  $("view-map").addEventListener("click", () => setView("map"));
  $("modal-close").addEventListener("click", () => ($("modal").hidden = true));
  
  $("modal").addEventListener("click", (e) => {
    if (e.target.id === "modal") $("modal").hidden = true;
  });
  
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("modal").hidden = true;
  });

  // Global window listeners for drag panning bounds handling
  window.addEventListener("mousemove", (e) => {
    if (!isPanning) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) > dragThreshold || Math.abs(dy) > dragThreshold) {
      dragMoved = true;
    }
    offsetX = lastMouseX + dx;
    offsetY = lastMouseY + dy;
    constrainOffsets();
    updateMapTransform();
  });

  window.addEventListener("mouseup", () => {
    if (!isPanning) return;
    isPanning = false;
    const svg = $("map-svg").querySelector("svg");
    if (svg) svg.style.cursor = "";
  });

  // Bind map zoom controls UI elements
  const zoomInBtn = $("map-zoom-in");
  const zoomOutBtn = $("map-zoom-out");
  const zoomResetBtn = $("map-zoom-reset");
  
  if (zoomInBtn) {
    zoomInBtn.addEventListener("click", () => {
      zoomAt(1.5, 500, 210);
    });
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener("click", () => {
      zoomAt(1 / 1.5, 500, 210);
    });
  }
  if (zoomResetBtn) {
    zoomResetBtn.addEventListener("click", () => {
      scale = 1;
      offsetX = 0;
      offsetY = 0;
      updateMapTransform();
    });
  }
}

(async function init() {
  const t = Date.now();
  const data = await fetchJson([`jurisdictions.json?t=${t}`, `../data/jurisdictions.json?t=${t}`]);
  if (!data) {
    $("rows").innerHTML = `<tr><td colspan="7">Failed to load data.</td></tr>`;
    return;
  }
  ALL = data.jurisdictions || [];
  BY_ID = Object.fromEntries(ALL.map((j) => [j.id, j]));
  fillSelect($("continent"),
    CONTINENT_ORDER.filter((c) => ALL.some((j) => j.continent === c)));
  fillSelect($("status"), ["Banned", "Restricted", "Active", "Pending", "None"]
    .filter((s) => ALL.some((j) => j.status === s)));
  updateCountrySelect();
  $("meta-line").textContent =
    `${ALL.length} jurisdictions · last refresh ${data.meta?.last_full_refresh || "—"} · ` +
    `updates checked daily`;
  
  const trackedKpiNum = document.querySelector("#kpi-tracked .kpi-num");
  if (trackedKpiNum) {
    trackedKpiNum.textContent = ALL.length;
  }
  
  const monitoredKpiNum = document.querySelector("#kpi-monitored .kpi-num");
  if (monitoredKpiNum) {
    const totalListings = ALL.reduce((sum, j) => sum + (j.active_listings || 0), 0);
    monitoredKpiNum.textContent = totalListings.toLocaleString();
  }
  
  wire();
  setupWizard();
  setupSubscribeDialog();
  render();

  const changelog = await fetchJson([`changelog.json?t=${t}`, `../data/changelog.json?t=${t}`]);
  renderLatest(changelog);

  // DevTools deterrents: disable right-click and open shortcuts
  document.addEventListener('contextmenu', e => e.preventDefault());
  document.addEventListener('keydown', e => {
    if (
      e.key === 'F12' ||
      (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C' || e.key === 'i' || e.key === 'j' || e.key === 'c')) ||
      (e.metaKey && e.altKey && (e.key === 'i' || e.key === 'I' || e.key === 'j' || e.key === 'J'))
    ) {
      e.preventDefault();
    }
  });
})();
function updateKpiCardActiveStates() {
  const statusSelect = $("status");
  if (!statusSelect) return;
  const status = statusSelect.value;
  
  $("kpi-bans").classList.toggle("active", status === "Banned");
  $("kpi-caps").classList.toggle("active", status === "Restricted");
  $("kpi-allowed").classList.toggle("active", status === "Active");
  $("kpi-tracked").classList.toggle("active", !status);
  $("kpi-monitored").classList.toggle("active", !status);
}

function showToast(message) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  
  // Clear any existing toasts to avoid spamming
  container.innerHTML = "";
  
  const toast = document.createElement("div");
  toast.className = "toast-message";
  toast.innerHTML = `
    <div class="toast-body">
      <i class="fa-solid fa-circle-info toast-icon"></i>
      <span class="toast-text">${message}</span>
    </div>
  `;
  
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.classList.add("show");
  }, 10);
  
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 4000);
}

