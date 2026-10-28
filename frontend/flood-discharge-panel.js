(() => {
  "use strict";

  const DISTRICTS = {
    patna: "Patna · Gandhighat",
    muzaffarpur: "Muzaffarpur · Sikandarpur"
  };
  const panelId = "openMeteoDischargePanel";
  const style = document.createElement("style");
  style.textContent = `
    #${panelId} { margin-top:1rem; min-width:0; }
    #${panelId} .discharge-status { color:var(--muted,#a8b4c8); font-size:.9rem; overflow-wrap:anywhere; }
    #${panelId} .discharge-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:.65rem; margin:.8rem 0; }
    #${panelId} .discharge-metric { border:1px solid rgba(148,163,184,.2); border-radius:10px; padding:.7rem; min-width:0; }
    #${panelId} .discharge-metric span { display:block; font-size:.78rem; opacity:.8; margin-bottom:.35rem; overflow-wrap:anywhere; }
    #${panelId} .discharge-metric strong { overflow-wrap:anywhere; }
    #${panelId} .discharge-table-wrap { width:100%; overflow:auto; }
    #${panelId} table { width:100%; border-collapse:collapse; font-size:.86rem; white-space:nowrap; }
    #${panelId} th,#${panelId} td { text-align:left; padding:.55rem .45rem; border-bottom:1px solid rgba(148,163,184,.18); }
    #${panelId} th { position:sticky; top:0; background:var(--panel,#101827); }
    #${panelId} .discharge-note { font-size:.82rem; line-height:1.5; opacity:.85; }
    #${panelId} .discharge-meta { display:flex; flex-wrap:wrap; gap:.45rem .9rem; font-size:.8rem; opacity:.85; }
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
      <div class="discharge-table-wrap"><table><thead id="dischargeHead"></thead><tbody id="dischargeRows"><tr><td>Waiting for API response…</td></tr></tbody></table></div>
      <p id="dischargeFetched" class="discharge-meta"></p>
      <p class="discharge-note">Hydrological model output only. Not a flood probability or official warning, and not included in the CWC model percentage. Follow official CWC/IMD and disaster-management guidance.</p>
      <a href="https://open-meteo.com/en/docs/flood-api" target="_blank" rel="noreferrer">Open-Meteo Flood API documentation ↗</a>
    `;
    host.appendChild(section);
  }

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
  }

  function numericValues(value) {
    if (typeof value === "number" && Number.isFinite(value)) return [value];
    if (Array.isArray(value)) return value.filter((item) => typeof item === "number" && Number.isFinite(item));
    return [];
  }

  function fmt(value, unit) {
    const values = numericValues(value);
    if (!values.length) return "—";
    const formatted = values.length === 1
      ? values[0].toLocaleString("en-IN", { maximumFractionDigits: 1 })
      : values.length + " ensemble values";
    return formatted + (unit ? " " + unit : "");
  }

  function localDateInIndia() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit"
    }).format(new Date());
  }

  async function refresh() {
    addPanel();
    const select = document.getElementById("districtSelect");
    const district = select && DISTRICTS[select.value] ? select.value : "patna";
    const badge = document.getElementById("dischargeBadge");
    const location = document.getElementById("dischargeLocation");
    const metrics = document.getElementById("dischargeMetrics");
    const head = document.getElementById("dischargeHead");
    const rows = document.getElementById("dischargeRows");
    const fetched = document.getElementById("dischargeFetched");
    if (!badge || !location || !metrics || !head || !rows || !fetched) return;

    badge.textContent = "Loading";
    badge.dataset.state = "stale";
    location.textContent = "Fetching Open-Meteo data for " + DISTRICTS[district] + "…";
    try {
      const response = await fetch("/api/bihar-live/flood-discharge?district=" + encodeURIComponent(district), {
        cache: "no-store", headers: { Accept: "application/json" }
      });
      let data;
      try { data = await response.json(); } catch { throw new Error("The server returned an unreadable response."); }
      if (!response.ok || !data || !data.available) {
        throw new Error((data && (data.message || data.error)) || "River-discharge data is temporarily unavailable.");
      }

      const daily = data.daily && typeof data.daily === "object" ? data.daily : {};
      const dates = Array.isArray(daily.time) ? daily.time : [];
      const units = data.units && typeof data.units === "object" ? data.units : {};
      const seriesKeys = Object.keys(daily).filter((key) =>
        key !== "time" && key.startsWith("river_discharge") && Array.isArray(daily[key])
      );
      if (!dates.length || !seriesKeys.length) {
        throw new Error("The API response did not contain a date timeline and discharge series.");
      }

      const currentDate = localDateInIndia();
      let currentIndex = dates.findIndex((date) => date >= currentDate);
      if (currentIndex < 0) currentIndex = dates.length - 1;
      const unitFor = (key) => units[key] || units.river_discharge || "";
      const labelFor = (key) => key.replace(/^river_discharge_?/, "").replace(/_/g, " ") || "river discharge";
      const usableKeys = seriesKeys.filter((key) => daily[key].some((value) => numericValues(value).length));
      const displayKeys = usableKeys.length ? usableKeys : seriesKeys;

      badge.textContent = "Live API";
      badge.dataset.state = "ok";
      location.textContent = data.location + " · " + displayKeys.length +
        " discharge series returned · forecast models requested: " +
        ((data.models_requested || []).join(", ") || "provider default");
      metrics.innerHTML = displayKeys.map((key) =>
        '<div class="discharge-metric"><span>' + esc(labelFor(key)) + ' · ' + esc(dates[currentIndex] || "latest") +
        '</span><strong>' + esc(fmt(daily[key][currentIndex], unitFor(key))) + '</strong></div>'
      ).join("");

      head.innerHTML = "<tr><th>Date</th>" + displayKeys.map((key) =>
        "<th>" + esc(labelFor(key)) + (unitFor(key) ? " (" + esc(unitFor(key)) + ")" : "") + "</th>"
      ).join("") + "</tr>";
      rows.innerHTML = dates.map((date, index) =>
        "<tr><td>" + esc(date) + "</td>" + displayKeys.map((key) =>
          "<td>" + esc(fmt(daily[key][index], unitFor(key))) + "</td>"
        ).join("") + "</tr>"
      ).join("");

      fetched.textContent = "Source: " + (data.source || "Open-Meteo Flood API") +
        " · fetched " + (data.fetched_at_utc || "time unavailable") +
        " · timezone: " + (data.timezone || "provider timezone") +
        (data.cache_age_seconds != null ? " · cache age " + data.cache_age_seconds + "s" : "");
    } catch (error) {
      badge.textContent = "Unavailable";
      badge.dataset.state = "stale";
      location.textContent = error && error.message ? error.message : "River-discharge API is temporarily unavailable.";
      metrics.innerHTML = "";
      head.innerHTML = "<tr><th>Date</th><th>Discharge series</th></tr>";
      rows.innerHTML = '<tr><td colspan="2">No live values available. Retry later; no values are estimated or substituted.</td></tr>';
      fetched.textContent = "";
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