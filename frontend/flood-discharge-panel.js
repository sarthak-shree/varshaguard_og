(() => {
  "use strict";

  const DISTRICTS = {
    patna: "Patna · Gandhighat",
    muzaffarpur: "Muzaffarpur · Sikandarpur"
  };
  const panelId = "openMeteoDischargePanel";
  const style = document.createElement("style");
  style.textContent = `
    #${panelId} { margin-top: 1rem; }
    #${panelId} .discharge-status { color: var(--muted, #a8b4c8); font-size: .9rem; }
    #${panelId} .discharge-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(125px,1fr)); gap:.65rem; margin:.8rem 0; }
    #${panelId} .discharge-metric { border:1px solid rgba(148,163,184,.2); border-radius:10px; padding:.7rem; min-width:0; }
    #${panelId} .discharge-metric span { display:block; font-size:.78rem; opacity:.8; margin-bottom:.35rem; }
    #${panelId} .discharge-metric strong { overflow-wrap:anywhere; }
    #${panelId} table { width:100%; border-collapse:collapse; font-size:.9rem; }
    #${panelId} th,#${panelId} td { text-align:left; padding:.5rem .35rem; border-bottom:1px solid rgba(148,163,184,.18); }
    #${panelId} .discharge-note { font-size:.82rem; line-height:1.5; opacity:.85; }
  `;
  document.head.appendChild(style);

  function addPanel() {
    const host = document.querySelector(".left-column") || document.querySelector("main");
    if (!host || document.getElementById(panelId)) return;
    const section = document.createElement("section");
    section.id = panelId;
    section.className = "panel";
    section.innerHTML = `
      <div class="panel-heading"><div><p class="small-title">OPEN-METEO · LIVE HYDROLOGY</p><h2>River discharge forecast</h2></div><span id="dischargeBadge" class="risk-trend" data-state="stale">Loading</span></div>
      <p id="dischargeLocation" class="discharge-status">Loading river-discharge data…</p>
      <div id="dischargeMetrics" class="discharge-grid"></div>
      <div style="overflow-x:auto"><table><thead><tr><th>Date</th><th>Daily discharge</th><th>Mean</th><th>Maximum</th></tr></thead><tbody id="dischargeRows"><tr><td colspan="4">Waiting for API response…</td></tr></tbody></table></div>
      <p id="dischargeFetched" class="discharge-status"></p>
      <p class="discharge-note">Hydrological model output only. Not a flood probability or official warning, and not included in the CWC model percentage. Follow official CWC/IMD and disaster-management guidance.</p>
      <a href="https://open-meteo.com/en/docs/flood-api" target="_blank" rel="noreferrer">Open-Meteo Flood API documentation ↗</a>
    `;
    host.appendChild(section);
  }

  function firstNumeric(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (Array.isArray(value)) {
      const values = value.filter((item) => typeof item === "number" && Number.isFinite(item)).sort((a, b) => a - b);
      if (values.length) return values[Math.floor(values.length / 2)];
    }
    return null;
  }

  function fmt(value, unit) {
    const number = firstNumeric(value);
    return number === null ? "—" : number.toLocaleString("en-IN", { maximumFractionDigits: 1 }) + (unit ? " " + unit : "");
  }

  async function refresh() {
    addPanel();
    const select = document.getElementById("districtSelect");
    const district = select && DISTRICTS[select.value] ? select.value : "patna";
    const badge = document.getElementById("dischargeBadge");
    const location = document.getElementById("dischargeLocation");
    const metrics = document.getElementById("dischargeMetrics");
    const rows = document.getElementById("dischargeRows");
    if (!badge || !location || !metrics || !rows) return;
    badge.textContent = "Loading";
    location.textContent = "Fetching Open-Meteo forecast for " + DISTRICTS[district] + "…";
    try {
      const response = await fetch("/api/bihar-live/flood-discharge?district=" + encodeURIComponent(district), {
        cache: "no-store",
        headers: { Accept: "application/json" }
      });
      const data = await response.json();
      if (!response.ok || !data.available) throw new Error(data.error || data.message || "Data is temporarily unavailable.");
      const daily = data.daily || {};
      const dates = Array.isArray(daily.time) ? daily.time : [];
      const units = data.units || {};
      const unit = units.river_discharge || "provider units";
      const mainKey = Array.isArray(daily.river_discharge) ? "river_discharge" :
        Object.keys(daily).find((key) => key.startsWith("river_discharge") && key !== "time");
      const meanKey = Array.isArray(daily.river_discharge_mean) ? "river_discharge_mean" : null;
      const maxKey = Array.isArray(daily.river_discharge_max) ? "river_discharge_max" : null;
      const currentIndex = dates.findIndex((date) => date >= new Date().toISOString().slice(0, 10));
      const index = currentIndex < 0 ? 0 : currentIndex;
      const mainValue = mainKey ? daily[mainKey][index] : null;
      const meanValue = meanKey ? daily[meanKey][index] : null;
      const maxValue = maxKey ? daily[maxKey][index] : null;
      badge.textContent = "Live API";
      badge.dataset.state = "ok";
      location.textContent = data.location + " · " + data.models_requested.length + " GloFAS model variants · ensemble requested";
      metrics.innerHTML = [
        ["Discharge", fmt(mainValue, unit)],
        ["Mean discharge", fmt(meanValue, unit)],
        ["Maximum discharge", fmt(maxValue, unit)]
      ].map(([label, value]) => '<div class="discharge-metric"><span>' + label + '</span><strong>' + value + '</strong></div>').join("");
      rows.innerHTML = dates.slice(0, 7).map((date, i) =>
        "<tr><td>" + date + "</td><td>" + fmt(mainKey ? daily[mainKey][i] : null, unit) +
        "</td><td>" + fmt(meanKey ? daily[meanKey][i] : null, unit) +
        "</td><td>" + fmt(maxKey ? daily[maxKey][i] : null, unit) + "</td></tr>"
      ).join("") || '<tr><td colspan="4">No daily values returned.</td></tr>';
      document.getElementById("dischargeFetched").textContent =
        "Fetched " + (data.fetched_at_utc || "recently") + " · " + (data.timezone || "provider timezone");
    } catch (error) {
      badge.textContent = "Unavailable";
      badge.dataset.state = "stale";
      location.textContent = error.message || "The river-discharge API is temporarily unavailable.";
      metrics.innerHTML = "";
      rows.innerHTML = '<tr><td colspan="4">No live discharge values available. Try again later.</td></tr>';
      document.getElementById("dischargeFetched").textContent = "";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    addPanel();
    refresh();
    const select = document.getElementById("districtSelect");
    if (select) select.addEventListener("change", refresh);
    window.setInterval(refresh, 15 * 60 * 1000);
  });
})();