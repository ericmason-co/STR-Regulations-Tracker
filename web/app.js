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
  "Serbia": "Republic of Serbia",
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
  const minY = 500 * (1 - scale) - 100;
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
  svg.setAttribute("viewBox", "0 0 1000 500");
  
  const viewport = document.createElementNS(NS, "g");
  viewport.id = "map-viewport";
  
  for (const f of geo.features) {
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
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const cx = (mouseX / rect.width) * 1000;
    const cy = (mouseY / rect.height) * 500;
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
    zoomAt(factor, cx, cy);
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

function openModal(j) {
  const rows = Object.keys(FIELD_LABELS)
    .map((k) => `<dt>${FIELD_LABELS[k]}</dt><dd>${linkify(j[k])}</dd>`)
    .join("");
  const rt = recentTag(j);
  const recent = rt ? " " + rt : "";
  const disp = displayName(j);
  const locParts = [...new Set([j.state !== disp.name ? j.state : null, j.country, j.continent].filter(Boolean))];
  $("modal-body").innerHTML = `
    <h2>${esc(disp.name)}${recent}</h2>
    <p class="loc">${esc(locParts.join(" · "))}</p>
    <dl class="field-grid">${rows}</dl>`;
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

  // Populate city dropdown (exlcuding level indicators where possible, sorted)
  const validCities = ALL.filter(j => !/^(state level|state|nationwide|national|eu-wide)$/i.test(j.city))
                        .sort((a, b) => a.city.localeCompare(b.city));
  
  validCities.forEach(j => {
    const opt = document.createElement("option");
    opt.value = j.id;
    opt.textContent = `${j.city}, ${j.state ? j.state + ', ' : ''}${j.country}`;
    citySelect.appendChild(opt);
  });

  citySelect.addEventListener("change", () => {
    next1.disabled = false;
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
  });

  $("wizard-prev-2").addEventListener("click", () => {
    $("wizard-step-2").style.display = "none";
    $("wizard-step-1").style.display = "block";
  });

  next2.addEventListener("click", () => {
    $("wizard-step-2").style.display = "none";
    $("wizard-step-3").style.display = "block";
  });

  $("wizard-prev-3").addEventListener("click", () => {
    $("wizard-step-3").style.display = "none";
    $("wizard-step-2").style.display = "block";
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
}

function wire() {
  $("continent").addEventListener("input", () => {
    updateCountrySelect();
    render();
  });
  
  ["search", "status", "country"].forEach((id) =>
    $(id).addEventListener("input", render));
  
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
      zoomAt(1.5, 500, 250);
    });
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener("click", () => {
      zoomAt(1 / 1.5, 500, 250);
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
  
  wire();
  setupWizard();
  render();

  const changelog = await fetchJson([`changelog.json?t=${t}`, `../data/changelog.json?t=${t}`]);
  renderLatest(changelog);
})();
// Deployment trigger comment v7

