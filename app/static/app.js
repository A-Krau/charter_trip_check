"use strict";

const $ = (sel) => document.querySelector(sel);
const DAY = 86400;
const state = { from: null, to: null, preset: "24h", result: null, selected: null };

// ---------- helpers ----------

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, params) {
  const url = new URL(path, location.origin);
  Object.entries(params || {}).forEach(([k, v]) => url.searchParams.set(k, v));
  const resp = await fetch(url);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.detail || `Request failed (HTTP ${resp.status})`);
  return body;
}

const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtDate = (t) => new Date(t * 1000).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
const fmtUtc = (t) => new Date(t * 1000).toISOString().slice(5, 16).replace("T", " ") + "Z";
const isoDay = (t) => new Date(t * 1000).toISOString().slice(0, 10);
function fmtDur(sec) {
  if (!(sec > 0)) return "";
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}
function toLocalInput(t) {
  const d = new Date(t * 1000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
const operatorOf = (f) => f.callsign_operator || f.operator || f.owner || "";

// ---------- map ----------

const map = L.map("map", { zoomControl: false, worldCopyJump: true, attributionControl: true }).setView([39.5, -96], 4);
L.control.zoom({ position: "bottomright" }).addTo(map);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  subdomains: "abcd", maxZoom: 18,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · Flights: <a href="https://opensky-network.org">OpenSky Network</a>',
}).addTo(map);

const routeLayer = L.layerGroup().addTo(map);
const trackLayer = L.layerGroup().addTo(map);

function greatCircle(a, b, n = 64) {
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const [la1, lo1, la2, lo2] = [a.lat * rad, a.lon * rad, b.lat * rad, b.lon * rad];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  if (d === 0) return [[a.lat, a.lon]];
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const f = i / n, A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2);
    const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2);
    const z = A * Math.sin(la1) + B * Math.sin(la2);
    pts.push([Math.atan2(z, Math.hypot(x, y)) * deg, Math.atan2(y, x) * deg]);
  }
  return pts;
}

function airportMarker(a) {
  return L.circleMarker([a.lat, a.lon], { radius: 6, color: "#fcc11d", weight: 2, fillColor: "#121315", fillOpacity: 1 })
    .bindTooltip(a.code, { permanent: true, direction: "top", offset: [0, -6], className: "apt-label" });
}

function drawRoute() {
  routeLayer.clearLayers();
  const pts = [state.from, state.to].filter(Boolean);
  pts.forEach((a) => airportMarker(a).addTo(routeLayer));
  if (pts.length === 2) {
    L.polyline(greatCircle(state.from, state.to), { color: "#fcc11d", weight: 2, opacity: .55, dashArray: "6 8" }).addTo(routeLayer);
    if (!state.selected) map.fitBounds(L.latLngBounds(pts.map((a) => [a.lat, a.lon])), fitPadding());
  } else if (pts.length === 1) {
    map.setView([pts[0].lat, pts[0].lon], 7);
  }
}

function fitPadding() {
  const wide = window.innerWidth > 760;
  return { paddingTopLeft: [wide ? 420 + (state.selected ? 360 : 0) : 30, 40], paddingBottomRight: [40, wide ? 40 : window.innerHeight * 0.62] };
}

const ALT_STOPS = [[0, [245, 196, 0]], [2000, [166, 217, 54]], [5000, [56, 200, 160]], [8000, [58, 143, 240]], [11000, [138, 92, 246]], [13000, [209, 79, 216]]];
function altColor(m) {
  m = Math.max(0, m || 0);
  for (let i = 1; i < ALT_STOPS.length; i++) {
    const [a0, c0] = ALT_STOPS[i - 1], [a1, c1] = ALT_STOPS[i];
    if (m <= a1) {
      const f = (m - a0) / (a1 - a0);
      return `rgb(${c0.map((c, j) => Math.round(c + (c1[j] - c) * f)).join(",")})`;
    }
  }
  return `rgb(${ALT_STOPS.at(-1)[1].join(",")})`;
}

function planeIcon(heading) {
  return L.divIcon({
    className: "plane-marker", iconSize: [28, 28], iconAnchor: [14, 14],
    html: `<svg viewBox="0 0 24 24" style="transform:rotate(${heading || 0}deg)"><use href="#plane"/></svg>`,
  });
}

function bearing(a, b) {
  const r = Math.PI / 180, y = Math.sin((b[1] - a[1]) * r) * Math.cos(b[0] * r);
  const x = Math.cos(a[0] * r) * Math.sin(b[0] * r) - Math.sin(a[0] * r) * Math.cos(b[0] * r) * Math.cos((b[1] - a[1]) * r);
  return (Math.atan2(y, x) / r + 360) % 360;
}

async function drawTrack(f) {
  trackLayer.clearLayers();
  $("#alt-legend").hidden = true;
  const note = $("#d-track");
  if (!f.departure.time) { note.textContent = ""; return; }
  note.innerHTML = '<span class="spinner"></span>Loading flight track…';
  try {
    const t = await api("/api/track", { icao24: f.icao24, time: f.departure.time + 60 });
    if (state.selected !== f) return;
    const path = t.path.filter((p) => p[1] != null && p[2] != null);
    for (let i = 1; i < path.length; i++) {
      L.polyline([[path[i - 1][1], path[i - 1][2]], [path[i][1], path[i][2]]], { color: altColor(path[i][3]), weight: 3, opacity: .95 }).addTo(trackLayer);
    }
    if (path.length) {
      const last = path.at(-1);
      const hdg = last[4] ?? (path.length > 1 ? bearing(path.at(-2).slice(1, 3), last.slice(1, 3)) : 0);
      L.marker([last[1], last[2]], { icon: planeIcon(hdg), interactive: false }).addTo(trackLayer);
      map.fitBounds(L.latLngBounds(path.map((p) => [p[1], p[2]])), fitPadding());
      $("#alt-legend").hidden = false;
    }
    note.textContent = `Track: ${path.length} positions from OpenSky.`;
  } catch (e) {
    if (state.selected === f) note.textContent = `No track: ${e.message}`;
  }
}

// ---------- airport autocomplete ----------

function setupAutocomplete(input, key) {
  const list = input.parentElement.querySelector(".ac-list");
  let items = [], active = -1, timer = null, seq = 0;

  const close = () => { list.hidden = true; active = -1; };
  const choose = (a) => {
    state[key] = a;
    input.value = `${a.code}${a.iata && a.iata !== a.code ? " / " + a.iata : ""} · ${a.name}`;
    input.classList.add("code-set");
    close();
    drawRoute();
  };
  const render = () => {
    list.innerHTML = items.map((a, i) => `<li role="option" data-i="${i}" class="${i === active ? "active" : ""}">
      <span class="ac-code">${esc(a.code)}</span><span class="ac-name">${esc(a.name)}</span>
      <span class="ac-place">${esc([a.municipality, a.country].filter(Boolean).join(", "))}</span></li>`).join("");
    list.hidden = items.length === 0;
  };

  input.addEventListener("input", () => {
    state[key] = null;
    input.classList.remove("code-set");
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { items = []; close(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const res = await api("/api/airports", { q, limit: 8 });
        if (mine !== seq) return;
        items = res; active = items.length ? 0 : -1; render();
      } catch { /* ignore */ }
    }, 150);
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { active = Math.min(items.length - 1, active + 1); render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(0, active - 1); render(); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { choose(items[active]); e.preventDefault(); }
    else if (e.key === "Escape") close();
  });
  input.addEventListener("focus", () => { if (state[key]) input.select(); });
  input.addEventListener("blur", () => setTimeout(close, 150));
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li");
    if (li) choose(items[+li.dataset.i]);
  });

  return {
    choose,
    // Resolve whatever was typed (e.g. "TEB") when no suggestion was picked.
    async resolve() {
      if (state[key]) return state[key];
      const q = input.value.trim().split(/[\s·/]/)[0];
      if (!q) return null;
      try { choose(await api(`/api/airports/${encodeURIComponent(q)}`)); } catch { return null; }
      return state[key];
    },
  };
}

const acFrom = setupAutocomplete($("#from"), "from");
const acTo = setupAutocomplete($("#to"), "to");

$("#swap").addEventListener("click", () => {
  const [a, b] = [state.from, state.to];
  const [va, vb] = [$("#from").value, $("#to").value];
  state.from = b; state.to = a;
  $("#from").value = vb; $("#to").value = va;
  $("#from").classList.toggle("code-set", !!b); $("#to").classList.toggle("code-set", !!a);
  drawRoute();
});

// ---------- time window ----------

function windowFor(preset) {
  const now = Math.floor(Date.now() / 1000);
  if (preset === "24h") return [now - DAY, now];
  if (preset === "3d") return [now - 3 * DAY, now];
  if (preset === "7d") return [now - 7 * DAY + 60, now];
  if (preset === "yesterday") {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    const midnight = Math.floor(d.getTime() / 1000);
    return [midnight - DAY, midnight - 1];
  }
  const b = Date.parse($("#begin").value) / 1000, e = Date.parse($("#end").value) / 1000;
  return [Math.floor(b), Math.floor(e)];
}

document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
  document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
  state.preset = chip.dataset.preset;
  const custom = state.preset === "custom";
  $("#custom-window").hidden = !custom;
  if (custom && !$("#begin").value) {
    const now = Math.floor(Date.now() / 1000);
    $("#begin").value = toLocalInput(now - 2 * DAY);
    $("#end").value = toLocalInput(now);
  }
}));

// ---------- search & results ----------

function showMessage(html, isError = false) {
  const m = $("#message");
  m.innerHTML = html; m.hidden = !html; m.classList.toggle("error", isError);
}

async function runSearch(e) {
  e?.preventDefault();
  const [from, to] = await Promise.all([acFrom.resolve(), acTo.resolve()]);
  if (!from || !to) { showMessage("Pick both airports from the suggestions.", true); return; }
  const [begin, end] = windowFor(state.preset);
  if (!(begin < end)) { showMessage("Set a start and an end for the custom window.", true); return; }

  closeDetail();
  $("#results").hidden = true;
  $("#go").disabled = true;
  showMessage('<span class="spinner"></span>Asking OpenSky for flights…');
  try {
    state.result = await api("/api/search", { from: from.code, to: to.code, begin, end });
    showMessage("");
    renderResults();
    const qs = new URLSearchParams({ from: from.code, to: to.code, w: state.preset });
    if (state.preset === "custom") { qs.set("b", begin); qs.set("e", end); }
    history.replaceState(null, "", "?" + qs);
  } catch (err) {
    showMessage(`<strong>Search failed.</strong> ${esc(err.message)}`, true);
  } finally {
    $("#go").disabled = false;
  }
}
$("#search-form").addEventListener("submit", runSearch);
$("#show-possible").addEventListener("change", renderResults);

function flightRow(f) {
  const li = document.createElement("li");
  li.className = "flight" + (f.match === "confirmed" ? "" : " unconfirmed") + (state.selected === f ? " selected" : "");
  const t = f.departure.time || f.arrival.time;
  const tag = f.match === "origin_only" ? "dest. unknown" : f.match === "dest_only" ? "origin unknown" : "";
  li.innerHTML = `
    <div class="flight-main">
      <span class="flight-reg">${esc(f.registration || f.icao24.toUpperCase())}</span>
      ${f.callsign ? `<span class="flight-cs">${esc(f.callsign)}</span>` : ""}
      ${f.typecode ? `<span class="type-badge">${esc(f.typecode)}</span>` : ""}
      ${tag ? `<span class="tag">${tag}</span>` : ""}
    </div>
    <div class="flight-time">${t ? fmtTime(t) : "–"}</div>
    <div class="flight-op">${esc(operatorOf(f) || f.model || "Operator unknown")}</div>
    <div class="flight-date">${t ? fmtDate(t) : ""}</div>`;
  li.addEventListener("click", () => selectFlight(f));
  return li;
}

function renderResults() {
  const r = state.result;
  if (!r) return;
  const confirmed = r.flights.filter((f) => f.match === "confirmed");
  const possible = r.flights.filter((f) => f.match !== "confirmed");
  const showPossible = $("#show-possible").checked;
  const list = $("#flight-list");
  list.innerHTML = "";

  $("#results").hidden = false;
  $("#results-summary").innerHTML = `<strong>${confirmed.length}</strong> confirmed flight${confirmed.length === 1 ? "" : "s"}` +
    (possible.length ? ` · ${possible.length} unconfirmed` : "");
  $("#topbar-route").hidden = false;
  $("#topbar-route").innerHTML = `<strong>${esc(r.origin.code)}</strong> → <strong>${esc(r.destination.code)}</strong> · ${fmtDate(r.begin)} – ${fmtDate(r.end)}`;

  const label = (text) => { const li = document.createElement("li"); li.className = "section-label"; li.textContent = text; list.append(li); };
  if (confirmed.length) {
    label(`${r.origin.code} → ${r.destination.code}`);
    confirmed.forEach((f) => list.append(flightRow(f)));
  } else {
    const li = document.createElement("li");
    li.className = "message";
    li.innerHTML = `No confirmed flights from <strong>${esc(r.origin.code)}</strong> to <strong>${esc(r.destination.code)}</strong> in this window.` +
      (r.end > Date.now() / 1000 - 1.5 * DAY ? " Recent flights may not be published yet." : "");
    list.append(li);
  }
  if (showPossible && possible.length) {
    label("Unconfirmed: one end not detected");
    possible.forEach((f) => list.append(flightRow(f)));
  }
}

// ---------- detail panel ----------

function selectFlight(f) {
  state.selected = f;
  renderResults();
  const reg = f.registration || f.icao24.toUpperCase();
  $("#d-callsign").textContent = f.callsign || reg;
  $("#d-sub").textContent = [f.callsign ? reg : "", f.typecode, operatorOf(f)].filter(Boolean).join(" · ");
  $("#d-dep-code").textContent = f.departure.airport || "?";
  $("#d-arr-code").textContent = f.arrival.airport || "?";
  $("#d-dep-time").textContent = f.departure.time ? `${fmtDate(f.departure.time)} ${fmtTime(f.departure.time)}` : "";
  $("#d-arr-time").textContent = f.arrival.time ? `${fmtDate(f.arrival.time)} ${fmtTime(f.arrival.time)}` : "";
  $("#d-dep-utc").textContent = f.departure.time ? fmtUtc(f.departure.time) : "";
  $("#d-arr-utc").textContent = f.arrival.time ? fmtUtc(f.arrival.time) : "";
  $("#d-dur").textContent = fmtDur(f.arrival.time - f.departure.time);

  const note = $("#d-match");
  note.classList.toggle("warn", f.match !== "confirmed");
  note.textContent = f.match === "confirmed"
    ? "Times are first and last seen by ADS-B receivers, close to takeoff and landing."
    : f.match === "origin_only"
      ? `Left ${state.result.origin.code}, but OpenSky could not tell where it landed. It may or may not have gone to ${state.result.destination.code}.`
      : `Landed at ${state.result.destination.code}, but OpenSky could not tell where it came from.`;

  const facts = [
    ["Registration", f.registration], ["Aircraft", [f.typecode, f.model].filter(Boolean).join(" · ")],
    ["Callsign", f.callsign],
    ["Callsign operator", f.callsign_operator !== f.operator ? f.callsign_operator : ""], ["Operator", f.operator],
    ["Owner", f.owner], ["Mode S hex", f.icao24.toUpperCase()],
  ].filter(([, v]) => v);
  $("#d-facts").innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");

  const links = [];
  const day = f.departure.time ? isoDay(f.departure.time) : "";
  links.push(["ADS-B Exchange", `https://globe.adsbexchange.com/?icao=${encodeURIComponent(f.icao24)}${day ? "&showTrace=" + day : ""}`]);
  if (f.registration) {
    links.push(["FlightAware", `https://www.flightaware.com/live/flight/${encodeURIComponent(f.registration)}`]);
    links.push(["Flightradar24", `https://www.flightradar24.com/data/aircraft/${encodeURIComponent(f.registration.toLowerCase())}`]);
    if (/^N\w+$/.test(f.registration)) {
      links.push(["FAA registry", `https://registry.faa.gov/AircraftInquiry/Search/NNumberResult?nNumberTxt=${encodeURIComponent(f.registration.slice(1))}`]);
    }
  }
  $("#d-links").innerHTML = links.map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${t} ↗</a>`).join("");

  $("#detail").hidden = false;
  document.body.classList.add("detail-open");
  drawTrack(f);
}

function closeDetail() {
  state.selected = null;
  $("#detail").hidden = true;
  document.body.classList.remove("detail-open");
  trackLayer.clearLayers();
  $("#alt-legend").hidden = true;
  if (state.result) renderResults();
}
$("#detail-close").addEventListener("click", () => { closeDetail(); drawRoute(); });

// ---------- CSV export ----------

$("#export").addEventListener("click", () => {
  const r = state.result;
  if (!r) return;
  const cols = ["match", "registration", "callsign", "typecode", "model", "callsign_operator", "operator", "owner", "icao24",
    "departure_airport", "departure_utc", "arrival_airport", "arrival_utc"];
  const iso = (t) => (t ? new Date(t * 1000).toISOString() : "");
  const rows = r.flights.map((f) => ({
    ...f, departure_airport: f.departure.airport, departure_utc: iso(f.departure.time),
    arrival_airport: f.arrival.airport, arrival_utc: iso(f.arrival.time),
  }));
  const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cols.join(","), ...rows.map((row) => cols.map((c) => cell(row[c])).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `${r.origin.code}-${r.destination.code}-${isoDay(r.begin)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---------- startup ----------

(async function init() {
  try {
    const s = await api("/api/status");
    const el = $("#api-status");
    el.textContent = s.authenticated ? "OpenSky account" : "OpenSky anonymous";
    el.classList.add(s.authenticated ? "ok" : "anon");
    el.title = s.authenticated ? "Using your OpenSky API client" : "No OpenSky credentials set; anonymous limits apply";
  } catch { /* status is cosmetic */ }

  const qs = new URLSearchParams(location.search);
  if (qs.get("w")) document.querySelector(`.chip[data-preset="${CSS.escape(qs.get("w"))}"]`)?.click();
  if (qs.get("w") === "custom" && qs.get("b") && qs.get("e")) {
    $("#begin").value = toLocalInput(+qs.get("b"));
    $("#end").value = toLocalInput(+qs.get("e"));
  }
  const load = async (code, ac) => { try { ac.choose(await api(`/api/airports/${encodeURIComponent(code)}`)); } catch { /* ignore */ } };
  if (qs.get("from")) await load(qs.get("from"), acFrom);
  if (qs.get("to")) await load(qs.get("to"), acTo);
  if (state.from && state.to) runSearch();
})();
