(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const API_BASE = ((location.hostname === "localhost" || location.hostname === "127.0.0.1") && location.port === "5001")
    ? "http://127.0.0.1:5002/api/bihar"
    : "/api/bihar";

  let records = [];
  let selectedStation = null;
  let selectedDistrict = "";
  let selectedLevel = "";
  let map = null;
  let markers = null;
  let coordinateIndex = {};
  let refreshTimer = null;

  const norm = (value) => String(value ?? "").trim().toLowerCase();
  const safe = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const numberOrNull = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const fmt = (value, digits = 2) => {
    const n = numberOrNull(value);
    return n === null ? "—" : n.toFixed(digits);
  };
  const observed = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-IN", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false
    });
  };
  const levelStatus = (record) => {
    const level = numberOrNull(record.water_level_m);
    const warning = numberOrNull(record.warning_level_m);
    const danger = numberOrNull(record.danger_level_m);
    if (level === null) return "normal";
    if (danger !== null && level >= danger) return "danger";
    if (warning !== null && level >= warning) return "warning";
    return "normal";
  };
  const statusLabel = (status) => status === "danger" ? "DANGER" : status === "warning" ? "WARNING" : "NORMAL";

  const el = {
    ring: $("apiRing"), status: $("apiStatusText"), meta: $("fetchMeta"), alert: $("alertStrip"),
    alertTitle: $("alertTitle"), alertMsg: $("alertMessage"), alertTime: $("alertTime"),
    search: $("stationSearch"), district: $("districtSelect"), level: $("statusSelect"), refresh: $("refreshButton"),
    count: $("observationCount"), danger: $("dangerCount"), warning: $("warningCount"), rising: $("risingCount"),
    table: $("riverTableBody"), detailStation: $("detailStation"), detailRiver: $("detailRiver"), detailStatus: $("detailStatus"),
    detailLevel: $("detailLevel"), detailWarning: $("detailWarning"), detailDanger: $("detailDanger"), detailHfl: $("detailHfl"),
    detailChange: $("detailChange"), detailTrend: $("detailTrend"), detailObserved: $("detailObserved"),
    warningMarker: $("warningMarker"), dangerMarker: $("dangerMarker"), levelMarker: $("levelMarker"), network: $("networkState"),
    error: $("errorCard"), errorText: $("errorMessage"), riskMetric: $("riskEngineMetric"), riskMetricState: $("riskEngineState"),
    riskBadge: $("riskEngineBadge"), riskScore: $("riskEngineScore"), riskLabel: $("riskEngineLabel"), riskProgress: $("riskProgress"),
    riskCopy: $("riskEngineCopy"), riskFactLevel: $("riskFactLevel"), riskFactRise: $("riskFactRise"), riskFactState: $("riskFactState"),
    inundBadge: $("inundationBadge"), inundScore: $("inundationScore"), inundLabel: $("inundationLabel"), inundProgress: $("inundationProgress"),
    inundCopy: $("inundationCopy"), inundGrid: $("inundationGrid"), inundMapLabel: $("inundationMapLabel"), inundExtent: $("inundationFactExtent"),
    inundDepth: $("inundationFactDepth"), inundConfidence: $("inundationFactConfidence"), map: $("biharMap"), mapStatus: $("mapStatus")
  };

  function setEngineLoading() {
    if (!el.riskScore) return;
    el.riskMetric.textContent = "—";
    el.riskMetricState.textContent = "loading";
    el.riskBadge.textContent = "LOADING";
    el.riskBadge.className = "engine-state";
    el.riskScore.textContent = "—%";
    el.riskLabel.textContent = "CHECKING";
    el.riskLabel.className = "engine-state";
    el.riskProgress.style.width = "0%";
    el.riskCopy.textContent = "Requesting the latest 24-hour flood-risk output.";
    el.inundBadge.textContent = "LOADING";
    el.inundScore.textContent = "—";
    el.inundLabel.textContent = "CHECKING";
    el.inundProgress.style.width = "0%";
    el.inundCopy.textContent = "Requesting the latest 24-hour inundation output.";
    el.inundExtent.textContent = "—";
    el.inundDepth.textContent = "—";
    el.inundConfidence.textContent = "—";
    el.inundMapLabel.textContent = "WAITING FOR MODEL";
    if (el.inundGrid) el.inundGrid.innerHTML = "";
  }

  function renderDistricts() {
    const districts = [...new Set(records.map(r => String(r.district || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    el.district.innerHTML = '<option value="">All Bihar</option>' + districts
      .map(d => `<option value="${safe(d)}">${safe(d)}</option>`).join("");
    el.district.value = selectedDistrict;
  }

  function filteredRecords() {
    const query = norm(el.search.value);
    return records.filter((r) => {
      const districtOk = !selectedDistrict || norm(r.district) === norm(selectedDistrict);
      const levelOk = !selectedLevel || levelStatus(r) === selectedLevel;
      const queryOk = !query || [r.station, r.river, r.district].some(v => norm(v).includes(query));
      return districtOk && levelOk && queryOk;
    });
  }

  function updateMetrics(list) {
    el.count.textContent = String(list.length);
    el.danger.textContent = String(list.filter(r => levelStatus(r) === "danger").length);
    el.warning.textContent = String(list.filter(r => levelStatus(r) === "warning").length);
    el.rising.textContent = String(list.filter(r => norm(r.trend) === "rising").length);
  }

  function updateAlert() {
    const danger = records.filter(r => levelStatus(r) === "danger");
    const warning = records.filter(r => levelStatus(r) === "warning");
    const rising = records.filter(r => norm(r.trend) === "rising");
    el.alert.classList.remove("danger", "warning", "normal");
    if (danger.length) {
      el.alert.classList.add("danger");
      el.alertTitle.textContent = `${danger.length} STATION${danger.length > 1 ? "S" : ""} AT / ABOVE DANGER LEVEL`;
      el.alertMsg.textContent = `${danger[0].station} is currently at ${fmt(danger[0].water_level_m)} m.`;
    } else if (warning.length) {
      el.alert.classList.add("warning");
      el.alertTitle.textContent = `${warning.length} STATION${warning.length > 1 ? "S" : ""} AT / ABOVE WARNING LEVEL`;
      el.alertMsg.textContent = `${warning[0].station} is currently at ${fmt(warning[0].water_level_m)} m.`;
    } else {
      el.alert.classList.add("normal");
      el.alertTitle.textContent = "NO STATION ABOVE WARNING LEVEL";
      el.alertMsg.textContent = rising.length ? `${rising.length} station${rising.length > 1 ? "s are" : " is"} currently rising.` : "All monitored stations are below warning level.";
    }
    el.alertTime.textContent = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function updateMap(list) {
    if (!map || !markers) return;
    markers.clearLayers();
    let mapped = 0;
    list.forEach(record => {
      const point = coordinateIndex[norm(record.station)];
      if (!point) return;
      const status = levelStatus(record);
      const color = status === "danger" ? "#b94a45" : status === "warning" ? "#a87514" : "#2e8b68";
      const marker = L.circleMarker([point[0], point[1]], {
        radius: status === "danger" ? 9 : 7,
        color, fillColor: color, fillOpacity: 0.85, weight: 2
      });
      marker.bindPopup(`<strong>${safe(record.station)}</strong><br>${safe(record.river)} • ${safe(record.district)}<br>Level: ${fmt(record.water_level_m)} m<br>Status: ${statusLabel(status)}<br><small>${observed(record.observed_at)}</small>`);
      marker.on("click", () => selectStation(record));
      markers.addLayer(marker);
      mapped += 1;
    });
    el.mapStatus.textContent = mapped ? `${mapped} mapped stations` : "Coordinates unavailable for current stations";
  }

  function renderTable() {
    const list = filteredRecords();
    updateMetrics(list);
    if (!list.length) {
      el.table.innerHTML = '<tr><td colspan="6" class="empty-state">No stations match the current filters.</td></tr>';
      updateMap(list);
      return;
    }
    el.table.innerHTML = list.map((record, index) => {
      const status = levelStatus(record);
      const selected = selectedStation && norm(selectedStation.station) === norm(record.station) && norm(selectedStation.district) === norm(record.district);
      const change = numberOrNull(record.water_level_m) !== null && numberOrNull(record.water_level_1h_before_m) !== null
        ? numberOrNull(record.water_level_m) - numberOrNull(record.water_level_1h_before_m) : null;
      return `<tr class="station-row ${selected ? "selected" : ""}" data-index="${index}"><td><button class="station-button" type="button"><strong>${safe(record.station)}</strong><span>${safe(record.river)}</span></button></td><td>${safe(record.district)}</td><td><strong class="level-value ${status}">${fmt(record.water_level_m)} m</strong></td><td><span class="threshold-badge ${status}">${statusLabel(status)}</span> <small>${fmt(status === "danger" ? record.danger_level_m : record.warning_level_m)} m</small></td><td><span class="trend ${safe(norm(record.trend))}"><i></i>${safe(record.trend || "Unknown")}</span></td><td>${observed(record.observed_at)}</td></tr>`;
    }).join("");
    el.table.querySelectorAll(".station-row").forEach((row, index) => row.addEventListener("click", () => selectStation(list[index])));
    updateMap(list);
  }

  function setDetail(record) {
    const status = levelStatus(record);
    const current = numberOrNull(record.water_level_m);
    const previous = numberOrNull(record.water_level_1h_before_m);
    const change = current !== null && previous !== null ? current - previous : null;
    el.detailStation.textContent = record.station || "Unknown station";
    el.detailRiver.textContent = `${record.river || "River"} • ${record.district || "Bihar"}`;
    el.detailStatus.textContent = statusLabel(status);
    el.detailStatus.className = `detail-status ${status}`;
    el.detailLevel.textContent = fmt(current);
    el.detailWarning.textContent = `${fmt(record.warning_level_m)} m`;
    el.detailDanger.textContent = `${fmt(record.danger_level_m)} m`;
    el.detailHfl.textContent = `${fmt(record.hfl_m)} m`;
    el.detailChange.textContent = change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)} m`;
    el.detailTrend.textContent = record.trend || "—";
    el.detailObserved.textContent = observed(record.observed_at);
    const warning = numberOrNull(record.warning_level_m);
    const danger = numberOrNull(record.danger_level_m);
    const hfl = numberOrNull(record.hfl_m);
    const max = Math.max(current ?? 0, warning ?? 0, danger ?? 0, hfl ?? 0, 1);
    const pos = (value) => `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
    el.warningMarker.style.left = warning === null ? "0%" : pos(warning);
    el.dangerMarker.style.left = danger === null ? "0%" : pos(danger);
    el.levelMarker.style.left = current === null ? "0%" : pos(current);
    el.levelMarker.className = `level-marker ${status}`;
  }

  function riskFromApi(data, record) {
    const probability = numberOrNull(data?.probability);
    const available = data?.probability_available === true || data?.available === true;
    const label = String(data?.risk_level || data?.risk || "").toUpperCase();
    if (!available || probability === null) {
      el.riskMetric.textContent = "—";
      el.riskMetricState.textContent = data?.method ? data.method.replaceAll("_", " ") : "not available";
      el.riskBadge.textContent = data?.method === "live_observation_baseline" ? "BASELINE" : "UNAVAILABLE";
      el.riskBadge.className = `engine-state ${data?.method === "live_observation_baseline" ? "advisory" : ""}`;
      el.riskScore.textContent = "—%";
      el.riskLabel.textContent = label || "NO VALIDATED MODEL";
      el.riskLabel.className = "engine-state";
      el.riskProgress.style.width = "0%";
      el.riskCopy.textContent = data?.message || "No validated 24-hour flood probability is available for this station.";
      return;
    }
    const pct = Math.max(0, Math.min(100, probability * 100));
    el.riskMetric.textContent = `${pct.toFixed(0)}%`;
    el.riskMetricState.textContent = data.calibrated === false ? "live baseline • not calibrated" : "model prediction";
    el.riskBadge.textContent = data.calibrated === false ? "BASELINE" : "MODEL OUTPUT";
    el.riskBadge.className = `engine-state ${data.calibrated === false ? "advisory" : "live"}`;
    el.riskScore.textContent = `${pct.toFixed(0)}%`;
    el.riskLabel.textContent = label || "PREDICTION";
    el.riskLabel.className = `engine-state ${label.includes("HIGH") ? "advisory" : "live"}`;
    el.riskProgress.style.width = `${pct}%`;
    el.riskCopy.textContent = data?.message || "24-hour flood-risk estimate returned from the Bihar pipeline.";
  }

  function inundationFromApi(data) {
    const extent = numberOrNull(data?.extent_percent);
    const depth = numberOrNull(data?.depth_m);
    const confidence = numberOrNull(data?.confidence);
    const available = data?.available === true && extent !== null && depth !== null;
    if (!available) {
      el.inundBadge.textContent = "NOT AVAILABLE";
      el.inundBadge.className = "engine-state advisory";
      el.inundScore.textContent = "—";
      el.inundLabel.textContent = "NO VALIDATED EXTENT";
      el.inundLabel.className = "engine-state advisory";
      el.inundProgress.style.width = "0%";
      el.inundExtent.textContent = "—";
      el.inundDepth.textContent = "—";
      el.inundConfidence.textContent = "—";
      el.inundCopy.textContent = data?.message || "A validated spatial inundation model is not connected yet.";
      el.inundMapLabel.textContent = "NO VALIDATED MAP";
      return;
    }
    el.inundBadge.textContent = data.physical_model === false ? "SPATIAL PROXY" : "MODEL OUTPUT";
    el.inundBadge.className = `engine-state ${data.physical_model === false ? "advisory" : "live"}`;
    el.inundScore.textContent = `${extent.toFixed(1)}%`;
    el.inundLabel.textContent = data.physical_model === false ? "PROXY EXTENT" : "PREDICTED EXTENT";
    el.inundLabel.className = `engine-state ${data.physical_model === false ? "advisory" : "live"}`;
    el.inundProgress.style.width = `${Math.max(0, Math.min(100, extent))}%`;
    el.inundExtent.textContent = `${extent.toFixed(1)}%`;
    el.inundDepth.textContent = `${depth.toFixed(2)} m`;
    el.inundConfidence.textContent = confidence === null ? "—" : `${(confidence <= 1 ? confidence * 100 : confidence).toFixed(0)}%`;
    el.inundCopy.textContent = data?.message || "24-hour inundation output returned for the selected station.";
    el.inundMapLabel.textContent = data.physical_model === false ? "PROXY • NOT A FLOOD MAP" : "MODEL OUTPUT";
  }

  async function fetchJson(path, params = {}) {
    const query = new URLSearchParams(params).toString();
    const response = await fetch(`${API_BASE}/${path}${query ? `?${query}` : ""}`, { headers: { Accept: "application/json" }, cache: "no-store" });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error || `${response.status} ${response.statusText}`);
    return payload;
  }

  async function loadEngines(record) {
    if (!record) return;
    setEngineLoading();
    const params = { station: record.station || "", district: record.district || "", river: record.river || "" };
    const change = numberOrNull(record.water_level_m) !== null && numberOrNull(record.water_level_1h_before_m) !== null
      ? numberOrNull(record.water_level_m) - numberOrNull(record.water_level_1h_before_m) : null;
    el.riskFactLevel.textContent = `${fmt(record.water_level_m)} m`;
    el.riskFactRise.textContent = change === null ? String(record.trend || "—") : `${change >= 0 ? "+" : ""}${change.toFixed(2)} m`;
    el.riskFactState.textContent = statusLabel(levelStatus(record));
    const results = await Promise.allSettled([fetchJson("risk", params), fetchJson("inundation", params)]);
    if (results[0].status === "fulfilled") riskFromApi(results[0].value, record);
    else {
      el.riskBadge.textContent = "OFFLINE";
      el.riskBadge.className = "engine-state advisory";
      el.riskLabel.textContent = "UNAVAILABLE";
      el.riskCopy.textContent = results[0].reason?.message || "Risk engine request failed.";
    }
    if (results[1].status === "fulfilled") inundationFromApi(results[1].value);
    else {
      el.inundBadge.textContent = "OFFLINE";
      el.inundBadge.className = "engine-state advisory";
      el.inundLabel.textContent = "UNAVAILABLE";
      el.inundCopy.textContent = results[1].reason?.message || "Inundation engine request failed.";
    }
  }

  function selectStation(record) {
    selectedStation = record;
    setDetail(record);
    renderTable();
    loadEngines(record);
  }

  function initMap() {
    if (!el.map || typeof window.L === "undefined" || map) return;
    map = L.map(el.map, { zoomControl: true, scrollWheelZoom: true }).setView([25.0961, 85.3131], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
    markers = L.layerGroup().addTo(map);
  }

  async function loadCoordinates() {
    try {
      const response = await fetch("station_coordinates.json", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      coordinateIndex = {};
      Object.entries(payload.stations || {}).forEach(([key, value]) => {
        if (Array.isArray(value) && value.length === 2) coordinateIndex[norm(key)] = [Number(value[0]), Number(value[1])];
      });
    } catch (_) {
      coordinateIndex = {};
    }
  }

  async function load(force = false) {
    if (!el.refresh) return;
    el.error.hidden = true;
    el.refresh.disabled = true;
    el.status.textContent = "LOADING";
    try {
      const payload = await fetchJson("live-rivers", force ? { refresh: "true" } : {});
      records = Array.isArray(payload.records) ? payload.records : [];
      selectedDistrict = el.district.value || "";
      selectedLevel = el.level.value || "";
      renderDistricts();
      updateAlert();
      renderTable();
      el.status.textContent = "LIVE";
      el.meta.textContent = `${records.length} stations • updated ${observed(payload.fetched_at)}`;
      el.ring.classList.add("online");
      el.ring.classList.remove("offline");
      el.network.textContent = "NETWORK ONLINE";
      if (!selectedStation && records.length) selectStation(records[0]);
      else if (selectedStation) {
        const match = records.find(r => norm(r.station) === norm(selectedStation.station) && norm(r.district) === norm(selectedStation.district));
        if (match) selectStation(match); else selectedStation = null;
      }
    } catch (error) {
      el.status.textContent = "OFFLINE";
      el.meta.textContent = "Live API unavailable";
      el.ring.classList.add("offline");
      el.ring.classList.remove("online");
      el.network.textContent = "NETWORK OFFLINE";
      el.error.hidden = false;
      el.errorText.textContent = error.message || "Unable to fetch Bihar river observations.";
    } finally {
      el.refresh.disabled = false;
    }
  }

  el.search?.addEventListener("input", renderTable);
  el.district?.addEventListener("change", () => { selectedDistrict = el.district.value; renderTable(); });
  el.level?.addEventListener("change", () => { selectedLevel = el.level.value; renderTable(); });
  el.refresh?.addEventListener("click", () => load(true));

  (async function boot() {
    initMap();
    await loadCoordinates();
    await load(false);
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => load(false), 5 * 60 * 1000);
  })();
})();
