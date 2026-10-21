(() => {
  "use strict";

  const API = "/api/bihar-live";
  const DISTRICTS = {
    patna: { name: "Patna", center: [25.5941, 85.1376] },
    muzaffarpur: { name: "Muzaffarpur", center: [26.1209, 85.3647] }
  };
  const $ = (id) => document.getElementById(id);
  let map = null;
  let districtLayer = null;
  let userMarker = null;
  let currentData = {};
  let refreshTimer = null;
  let leadTimer = null;

  async function getJson(path, options = {}) {
    const response = await fetch(path, { cache: "no-store", ...options });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The service returned an unreadable response."); }
    if (!response.ok || data.success === false) {
      throw new Error(data.error || "The Bihar Live service could not be reached.");
    }
    return data;
  }

  function showError(message) {
    const box = $("message");
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function clearError() {
    $("message").classList.add("hidden");
    $("message").textContent = "";
  }

  function setText(id, value) {
    const node = $(id);
    if (node) node.textContent = value;
  }

  function formatNumber(value, digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "—";
  }

  function friendlyStatus(value) {
    const status = String(value || "unknown").replaceAll("_", " ");
    return status;
  }

  function updateDashboard(health, fusion, evaluation, sources) {
    currentData = { health, fusion, evaluation, sources };
    const synthetic = String(health.mode || "").toLowerCase() === "synthetic";
    const modeLabel = health.badge || (synthetic ? "Synthetic demo data" : "Real data");
    setText("dataMode", synthetic ? "Demo only" : modeLabel);
    setText("dataBadge", modeLabel);
    setText("fusionMode", synthetic ? "Synthetic demo" : modeLabel);
    setText("statusNote", synthetic
      ? "This screen is using clearly labelled demo inputs. It is not a live flood warning."
      : "Provider status is shown below. This prototype is not an official flood warning.");
    setText("horizonValue", health.horizon_hours || 72);
    setText("serviceName", health.project || "Bihar Live prototype");
    setText("lastUpdated", new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" }));

    const estimate = fusion.estimate_mm;
    setText("rainEstimate", Number.isFinite(Number(estimate)) ? formatNumber(estimate, 1) + " mm" : "—");
    setText("rainEstimateNote", synthetic ? "Synthetic fusion estimate" : "Fusion output");
    setText("leadValue", fusion.lead_hours || $("leadSelect").value);
    setText("leadMetric", fusion.lead_hours || $("leadSelect").value);
    setText("maeMetric", formatNumber(evaluation.mae, 2));
    setText("rmseMetric", formatNumber(evaluation.rmse, 2));
    setText("sourceSubtitle", sources.mode === "synthetic" ? "Demo mode is active" : "Provider readiness");
    setText("sourceCount", (sources.sources || []).length + " SOURCES");

    const weightRoot = $("signalWeights");
    weightRoot.replaceChildren();
    Object.entries(fusion.weights || {}).forEach(([name, value]) => {
      const item = document.createElement("div");
      item.className = "bihar-signal-item";
      const label = document.createElement("span");
      label.textContent = name + " signal";
      const amount = document.createElement("strong");
      amount.textContent = Math.round(Number(value) * 100) + "%";
      item.append(label, amount);
      weightRoot.appendChild(item);
    });

    const sourceRoot = $("sourceList");
    sourceRoot.replaceChildren();
    (sources.sources || []).forEach((source) => {
      const item = document.createElement("div");
      item.className = "bihar-source-item";
      const label = document.createElement("span");
      label.textContent = source.name;
      const status = document.createElement("strong");
      status.textContent = friendlyStatus(source.status);
      status.dataset.state = source.status || "unknown";
      item.append(label, status);
      sourceRoot.appendChild(item);
    });

    setText("selectedDistrict", DISTRICTS[$("districtSelect").value].name);
    setText("leadMetric", $("leadSelect").value);
    clearError();
  }

  async function loadDashboard() {
    try {
      const lead = Number($("leadSelect").value);
      const responses = await Promise.all([
        getJson(API + "/health"),
        getJson(API + "/fusion?lead=" + encodeURIComponent(lead)),
        getJson(API + "/model/evaluation"),
        getJson(API + "/sources")
      ]);
      updateDashboard(...responses);
    } catch (error) {
      showError(error.message);
      setText("dataMode", "Unavailable");
      setText("dataBadge", "Service unavailable");
      setText("statusNote", "The Bihar Live API could not be reached. No current estimate is shown.");
    }
  }

  function setupMap() {
    if (!window.L || !$("map")) return;
    map = L.map("map").setView([25.86, 85.24], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);
    districtLayer = L.layerGroup().addTo(map);
    Object.entries(DISTRICTS).forEach(([key, district]) => {
      const color = key === "patna" ? "#34D399" : "#FBBF24";
      L.circleMarker(district.center, {
        radius: 9, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1
      }).addTo(districtLayer).bindPopup("<strong>" + district.name + "</strong><br>District map point");
    });
  }

  function selectDistrict() {
    const key = $("districtSelect").value;
    const district = DISTRICTS[key];
    setText("selectedDistrict", district.name);
    if (map) map.setView(district.center, 9, { animate: true });
    $("assistantInput").placeholder = "Ask about " + district.name + " and this dashboard";
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      showError("Location access is not available in this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const point = [position.coords.latitude, position.coords.longitude];
        if (!userMarker) {
          userMarker = L.circleMarker(point, {
            radius: 8, color: "#fff", weight: 3, fillColor: "#F87171", fillOpacity: 1
          }).addTo(map);
        } else {
          userMarker.setLatLng(point);
        }
        userMarker.bindPopup("Your current location").openPopup();
        $("userLocationLegend").hidden = false;
        map.setView(point, 11, { animate: true });
        clearError();
      },
      () => showError("Location permission was not granted. You can still use the district map."),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  }

  function buildAssistantContext() {
    const selected = DISTRICTS[$("districtSelect").value];
    return {
      dashboard: "Bihar Live VarshaGuard prototype",
      district: selected.name,
      data_mode: currentData.health?.mode || "unknown",
      status: currentData.health?.badge || "unknown",
      rainfall_fusion_estimate_mm: currentData.fusion?.estimate_mm ?? "unavailable",
      forecast_lead_hours: currentData.fusion?.lead_hours ?? $("leadSelect").value,
      fusion_weights: currentData.fusion?.weights || {},
      baseline_evaluation: currentData.evaluation
        ? { mae: currentData.evaluation.mae, rmse: currentData.evaluation.rmse, data_mode: currentData.evaluation.data_mode }
        : "unavailable",
      data_sources: (currentData.sources?.sources || []).map((source) => ({
        name: source.name, status: source.status
      })),
      limitation: "Prototype only. Rainfall fusion output is not a flood probability or official alert. Do not invent missing observations or forecasts."
    };
  }

  function appendAssistantMessage(text, role = "bot") {
    const item = document.createElement("div");
    item.className = "assistant-message " + (role === "user" ? "assistant-user" : role === "error" ? "assistant-error" : "assistant-bot");
    item.textContent = text;
    $("assistantMessages").appendChild(item);
    $("assistantMessages").scrollTop = $("assistantMessages").scrollHeight;
  }

  function setupAssistant() {
    const modal = $("assistantModal");
    const input = $("assistantInput");
    const form = $("assistantForm");
    const send = $("assistantSendButton");
    const open = () => { modal.classList.remove("hidden"); input.focus(); };
    const close = () => modal.classList.add("hidden");
    $("assistantTopButton").addEventListener("click", open);
    $("assistantOpenButton").addEventListener("click", open);
    $("assistantCloseButton").addEventListener("click", close);
    modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;
      appendAssistantMessage(question, "user");
      input.value = "";
      input.disabled = true;
      send.disabled = true;
      send.textContent = "Thinking…";
      try {
        const response = await fetch("/api/assistant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: question, context: buildAssistantContext() })
        });
        const data = await response.json();
        if (!response.ok || data.success === false) throw new Error(data.error || "Assistant request failed.");
        appendAssistantMessage(data.answer || "No answer returned.");
      } catch (error) {
        appendAssistantMessage(error.message, "error");
      } finally {
        input.disabled = false;
        send.disabled = false;
        send.textContent = "Send";
        input.focus();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupMap();
    setupAssistant();
    $("districtSelect").addEventListener("change", selectDistrict);
    $("leadSelect").addEventListener("input", () => {
      setText("leadValue", $("leadSelect").value);
      setText("leadMetric", $("leadSelect").value);
      window.clearTimeout(leadTimer);
      leadTimer = window.setTimeout(loadDashboard, 250);
    });
    $("locateButton").addEventListener("click", useMyLocation);
    $("mapRefreshButton").addEventListener("click", () => selectDistrict());
    selectDistrict();
    loadDashboard();
    refreshTimer = window.setInterval(loadDashboard, 60000);
    window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer), { once: true });
  });
})();
