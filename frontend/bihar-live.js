(() => {
  "use strict";

  const API = "/api/bihar-live/model/live";
  const DISTRICTS = {
    patna: { name: "Patna", center: [25.5941, 85.1376], prefix: "patna" },
    muzaffarpur: { name: "Muzaffarpur", center: [26.1209, 85.3647], prefix: "muzaffarpur" }
  };
  const REFRESH_MS = 5 * 60 * 1000;
  const $ = (id) => document.getElementById(id);
  let map = null;
  let stationLayer = null;
  let userMarker = null;
  let currentData = {};
  let refreshTimer = null;

  async function getJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The Bihar Live service returned an unreadable response."); }
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
    if (node) node.textContent = value == null ? "—" : String(value);
  }

  function finiteNumber(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value.length === 10 ? value + "T00:00:00+05:30" : value);
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata"
    });
  }

  function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value.includes("+") || value.endsWith("Z") ? value : value + "+05:30");
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("en-IN", {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata"
    }) + " IST";
  }

  function hoursAgo(value) {
    const hours = Number(value);
    if (!finiteNumber(value)) return "age unknown";
    if (hours < 1) return "less than 1 hour ago";
    return Math.round(hours) + " hour" + (Math.round(hours) === 1 ? "" : "s") + " ago";
  }

  function signalState(prediction) {
    if (!prediction || prediction.status === "stale" || prediction.status === "unavailable") return "stale";
    if (["danger_level_reached", "warning_level_reached"].includes(prediction.status)) return "high";
    if (["low", "medium", "high"].includes(prediction.risk_level)) return prediction.risk_level;
    if (!finiteNumber(prediction.model_probability) || !finiteNumber(prediction.decision_threshold)) return "stale";
    const probability = Number(prediction.model_probability);
    if (probability >= 0.5) return "high";
    return probability >= Number(prediction.decision_threshold) ? "medium" : "low";
  }

  function updateCard(districtKey, prediction) {
    const district = DISTRICTS[districtKey];
    const prefix = district.prefix;
    const signal = $(prefix + "Signal");
    const state = signalState(prediction);
    const label = prediction?.status === "danger_level_reached"
      ? "HIGH · danger observed"
      : prediction?.status === "warning_level_reached"
        ? "HIGH · warning observed"
        : prediction?.status === "stale"
          ? "No fresh estimate"
          : prediction?.status === "unavailable"
            ? "No live reading"
            : state === "high" ? "HIGH RISK" : state === "medium" ? "MEDIUM RISK" : state === "low" ? "LOW RISK" : "No estimate";

    signal.textContent = label;
    signal.dataset.state = state;
    const gaugeCard = $(prefix + "Card");
    gaugeCard.dataset.state = districtKey === $("districtSelect").value ? "selected" : "";
    gaugeCard.dataset.risk = state;
    setText(prefix + "Stage", finiteNumber(prediction?.current_stage_m) ? Number(prediction.current_stage_m).toFixed(2) + " m" : "—");
    setText(prefix + "Warning", finiteNumber(prediction?.warning_level_m) ? Number(prediction.warning_level_m).toFixed(2) + " m" : "—");
    setText(prefix + "Danger", finiteNumber(prediction?.danger_level_m) ? Number(prediction.danger_level_m).toFixed(2) + " m" : "—");
    setText(prefix + "Time", formatTime(prediction?.observed_at_ist));
    setText(prefix + "Rain", finiteNumber(prediction?.rainfall_24h_mm) ? Number(prediction.rainfall_24h_mm).toFixed(1) + " mm" : "—");

    const probabilityLabel = $(prefix + "Probability");
    const probabilityCaption = $(prefix + "ProbabilityLabel");
    let riskPercent = null;
    if (["danger_level_reached", "warning_level_reached"].includes(prediction?.status)) {
      riskPercent = 100;
      probabilityLabel.textContent = "100%";
      probabilityCaption.textContent = prediction.status === "danger_level_reached"
        ? "CWC danger level already reached (observed, not forecast)"
        : "CWC warning level already reached (observed, not forecast)";
      setText(prefix + "ForecastText", prediction.status === "danger_level_reached"
        ? "The latest CWC reading has reached the danger level. This is an observation, not a prediction."
        : "The latest CWC reading has reached the warning level. This is an observation, not a prediction.");
    } else if (prediction?.status === "predicted" && finiteNumber(prediction.model_probability)) {
      riskPercent = finiteNumber(prediction.risk_percentage)
        ? Number(prediction.risk_percentage)
        : Number(prediction.model_probability) * 100;
      probabilityLabel.textContent = riskPercent.toFixed(1) + "%";
      probabilityCaption.textContent = "Chance of reaching the CWC warning level in the next 24 hours";
      setText(prefix + "ForecastText", "From " + formatTime(prediction.forecast_start_ist) + " to " + formatTime(prediction.forecast_end_ist) + ": experimental estimate that this gauge may reach its CWC warning level.");
    } else {
      probabilityLabel.textContent = "—";
      probabilityCaption.textContent = "No model estimate shown";
      setText(prefix + "ForecastText", prediction?.message || "Waiting for recent, quality-checked CWC readings.");
    }

    const meter = $(prefix + "RiskMeter");
    const fill = $(prefix + "RiskFill");
    if (finiteNumber(riskPercent)) {
      const boundedPercent = Math.max(0, Math.min(100, riskPercent));
      meter.hidden = false;
      meter.setAttribute("aria-valuenow", boundedPercent.toFixed(1));
      meter.setAttribute("aria-valuetext", (state === "high" ? "High" : state === "medium" ? "Medium" : "Low") + " risk, " + boundedPercent.toFixed(1) + " percent");
      fill.style.width = boundedPercent + "%";
    } else {
      meter.hidden = true;
      meter.removeAttribute("aria-valuenow");
      meter.removeAttribute("aria-valuetext");
      fill.style.width = "0%";
    }

    const coverage = prediction?.feature_coverage;
    const coverageText = coverage ? "Model inputs available: " + coverage.available + " of " + coverage.total + ". " : "";
    const countText = finiteNumber(prediction?.observations_today)
      ? Number(prediction.observations_today) + " stage readings in today's summary. " : "";
    const partialText = prediction?.daily_summary_partial ? "Today's summary may be incomplete. " : "";
    const ageText = finiteNumber(prediction?.data_age_hours) ? "Latest reading " + hoursAgo(prediction.data_age_hours) + ". " : "";
    const maxText = finiteNumber(prediction?.daily_max_stage_m)
      ? "Today's highest stage was " + Number(prediction.daily_max_stage_m).toFixed(2) + " m. " : "";
    const validationText = prediction?.local_validation_note ? prediction.local_validation_note + " " : "";
    setText(prefix + "Quality", coverageText + countText + maxText + ageText + partialText + validationText + (prediction?.message && prediction.status !== "predicted" ? prediction.message : ""));
  }

  function makePopup(prediction) {
    const root = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = prediction.district + " · " + prediction.station_name;
    const reading = document.createElement("div");
    reading.textContent = finiteNumber(prediction.current_stage_m)
      ? "Latest level: " + Number(prediction.current_stage_m).toFixed(2) + " m"
      : "Latest level unavailable";
    const signal = document.createElement("div");
    if (prediction.status === "predicted") {
      const percent = finiteNumber(prediction.risk_percentage)
        ? Number(prediction.risk_percentage)
        : Number(prediction.model_probability) * 100;
      const riskLabel = (prediction.risk_level || "model").toUpperCase();
      signal.textContent = riskLabel + " risk · " + percent.toFixed(1) + "% chance of warning-level crossing in 24h";
    } else if (prediction.status === "danger_level_reached") {
      signal.textContent = "HIGH · 100% observed: danger level reached";
    } else if (prediction.status === "warning_level_reached") {
      signal.textContent = "HIGH · 100% observed: warning level reached";
    } else {
      signal.textContent = prediction.signal || prediction.message || "No current model estimate";
    }
    root.append(title, reading, signal);
    return root;
  }

  function markerColor(prediction) {
    const state = signalState(prediction);
    if (state === "high") return "#F87171";
    if (state === "medium") return "#FBBF24";
    if (state === "low") return "#34D399";
    return "#94A3B8";
  }

  function renderMap(predictions) {
    if (!map || !stationLayer) return;
    stationLayer.clearLayers();
    (predictions || []).forEach((prediction) => {
      const lat = Number(prediction.latitude);
      const lon = Number(prediction.longitude);
      if (!finiteNumber(prediction.latitude) || !finiteNumber(prediction.longitude)) return;
      L.circleMarker([lat, lon], {
        radius: 10, color: "#fff", weight: 3,
        fillColor: markerColor(prediction), fillOpacity: 1
      }).addTo(stationLayer).bindPopup(makePopup(prediction));
    });
  }

  function renderSources(data) {
    const source = data.source || {};
    const root = $("sourceList");
    root.replaceChildren();
    const total = Number(source.stations_in_model) || 13;
    const entries = [
      { name: "CWC river stage (HHS)", count: source.stations_with_recent_stage, rows: source.stage_rows_received },
      { name: "CWC rainfall (MPS)", count: source.stations_with_recent_rainfall, rows: source.rainfall_rows_received }
    ];
    entries.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "bihar-source-item";
      const label = document.createElement("span");
      label.textContent = entry.name;
      const status = document.createElement("strong");
      const count = Number(entry.count);
      status.textContent = finiteNumber(entry.count) ? count + "/" + total + " gauges" : "unavailable";
      status.dataset.state = finiteNumber(entry.count) && count > 0 ? (count === total ? "ready" : "partial") : "unavailable";
      item.append(label, status);
      root.appendChild(item);
    });
    setText("sourceSubtitle", data.available ? "Connected to the CWC Flood Forecast System" : "CWC readings are not available right now");
    setText("sourceCount", data.available ? "LIVE SOURCE" : "OFFLINE");
  }

  function updateDashboard(data) {
    currentData.live = data;
    const predictions = data.predictions || [];
    const byDistrict = Object.fromEntries(predictions.map((prediction) => [
      prediction.district?.toLowerCase(), prediction
    ]));
    updateCard("patna", byDistrict.patna);
    updateCard("muzaffarpur", byDistrict.muzaffarpur);
    const lowMediumBoundary = Number(data.risk_bands?.medium_min_inclusive_probability);
    if (Number.isFinite(lowMediumBoundary)) {
      const boundaryPercent = (lowMediumBoundary * 100).toFixed(1);
      setText("riskBandGuide", "LOW: under " + boundaryPercent + "%. MEDIUM: " + boundaryPercent + "% to under 50%. HIGH: 50% or more, or a CWC warning/danger level is already observed. Percent is the experimental chance of a gauge reaching its CWC warning level during the 24 hours after the latest reading—not a street or block flood probability.");
    }
    renderMap(predictions);
    renderSources(data);

    const card = $("connectionCard");
    if (!data.available) {
      card.dataset.state = "unavailable";
      setText("dataMode", "No live readings");
      setText("dataBadge", "CWC unavailable");
      setText("statusNote", data.error || "No current estimate is shown because live gauge data could not be loaded.");
      setText("stationCount", "0 of 2");
      setText("forecastBadge", "Waiting for CWC");
    } else {
      const current = predictions.filter((item) => finiteNumber(item.data_age_hours));
      const freshestAge = current.length ? Math.min(...current.map((item) => Number(item.data_age_hours))) : Infinity;
      const hasPrediction = predictions.some((item) => ["predicted", "danger_level_reached", "warning_level_reached"].includes(item.status));
      const state = freshestAge <= 6 ? "live" : "delayed";
      card.dataset.state = state;
      setText("dataMode", state === "live" ? "Live CWC readings" : "CWC update delayed");
      setText("dataBadge", freshestAge <= 6 ? "Updating" : "Check reading time");
      const insufficient = predictions.some((item) => item.status === "insufficient_inputs");
      setText("statusNote", hasPrediction
        ? "CWC readings are current. The model estimates warning-level risk during the 24 hours after the latest reading."
        : insufficient
          ? "CWC is connected, but not enough recent inputs are available for a 24-hour estimate."
          : "CWC connected, but recent quality-checked data is not available for the focus gauges.");
      const usable = predictions.filter((item) => ["predicted", "danger_level_reached", "warning_level_reached"].includes(item.status)).length;
      setText("stationCount", usable + " of 2");
      setText("forecastBadge", hasPrediction ? "CWC data connected" : "No current estimate");
    }
    setText("lastUpdated", formatTime(data.source?.latest_stage_at_ist || data.generated_at_ist));
    setText("selectedDistrict", DISTRICTS[$("districtSelect").value].name);
    clearError();
    selectDistrict(false);
  }

  async function loadDashboard() {
    try {
      const data = await getJson(API);
      updateDashboard(data);
      if (!data.available) showError(data.error || "CWC live data is currently unavailable.");
    } catch (error) {
      showError(error.message);
      updateCard("patna", { status: "unavailable", message: "No current estimate is shown because the service could not be reached." });
      updateCard("muzaffarpur", { status: "unavailable", message: "No current estimate is shown because the service could not be reached." });
      renderMap([]);
      $("connectionCard").dataset.state = "unavailable";
      setText("dataMode", "Service unavailable");
      setText("dataBadge", "No current estimate");
      setText("statusNote", "The Bihar Live service could not be reached. No current estimate is shown.");
      setText("forecastBadge", "Service unavailable");
      setText("patnaSignal", "No live reading");
      setText("muzaffarpurSignal", "No live reading");
    }
  }

  function setupMap() {
    if (!window.L || !$("map")) return;
    map = L.map("map").setView([25.86, 85.24], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);
    stationLayer = L.layerGroup().addTo(map);
  }

  function selectDistrict(moveMap = true) {
    const district = DISTRICTS[$("districtSelect").value];
    setText("selectedDistrict", district.name);
    Object.entries(DISTRICTS).forEach(([key, item]) => {
      const card = $(item.prefix + "Card");
      if (card) card.dataset.state = key === $("districtSelect").value ? "selected" : "";
    });
    if (!map || !moveMap) return;
    const prediction = (currentData.live?.predictions || []).find((item) => item.district?.toLowerCase() === district.name.toLowerCase());
    const center = prediction && Number.isFinite(Number(prediction.latitude))
      ? [Number(prediction.latitude), Number(prediction.longitude)] : district.center;
    map.setView(center, 10, { animate: true });
    $("assistantInput").placeholder = "Ask about " + district.name + " river readings";
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
      () => showError("Location permission was not granted. You can still choose Patna or Muzaffarpur."),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  }

  function buildAssistantContext() {
    const selected = DISTRICTS[$("districtSelect").value];
    const predictions = currentData.live?.predictions || [];
    return {
      dashboard: "VarshaGuard Bihar Live",
      district: selected.name,
      source: currentData.live?.source?.name || "unavailable",
      generated_at_ist: currentData.live?.generated_at_ist || "unavailable",
      selected_gauge: predictions.find((item) => item.district?.toLowerCase() === selected.name.toLowerCase()) || "unavailable",
      all_gauges: predictions,
      model_scope: currentData.live?.target_definition || "unavailable",
      risk_bands: currentData.live?.risk_bands || "unavailable",
      limitations: currentData.live?.limitations || ["No current data is available."],
      instruction: "Explain only these readings and the provided Low, Medium, or High band. Percentages estimate a gauge reaching its published CWC warning level during the 24 hours after the latest reading; they are not neighborhood flood probabilities or official warnings. Muzaffarpur has sparse holdout events, so say local accuracy is unknown. If readings are stale or inputs are insufficient, say no current estimate is available."
    };
  }

  function appendAssistantMessage(text, role = "bot") {
    const item = document.createElement("div");
    item.className = "assistant-message " + (role === "user" ? "assistant-user" : role === "error" ? "assistant-error" : "assistant-bot");
    item.textContent = text;
    $("assistantMessages").appendChild(item);
    $("assistantMessages").scrollTop = $("assistantMessages").scrollHeight;
    return item;
  }

  function setupAssistant() {
    const modal = $("assistantModal");
    const input = $("assistantInput");
    const form = $("assistantForm");
    const send = $("assistantSendButton");
    const voiceModeButton = $("assistantVoiceMode");
    let voiceControls = null;
    const setVoiceMode = (enabled) => {
      modal.querySelector(".assistant-dialog").dataset.assistantMode = enabled ? "voice" : "text";
      voiceModeButton?.setAttribute("aria-pressed", String(enabled));
      voiceModeButton?.classList.toggle("is-active", enabled);
      window.VarshaGuardOrb?.setState("idle");
      if (!enabled) input.focus();
    };
    voiceModeButton?.addEventListener("click", () => setVoiceMode(modal.querySelector(".assistant-dialog").dataset.assistantMode !== "voice"));
    const open = () => {
      modal.classList.remove("hidden");
      setVoiceMode(false);
      window.VarshaGuardOrb?.setState("idle");
      input.focus();
    };
    const close = () => { voiceControls?.cancel(); setVoiceMode(false); modal.classList.add("hidden"); };
    $("assistantTopButton").addEventListener("click", open);
    $("assistantOpenButton").addEventListener("click", open);
    document.querySelectorAll("[data-assistant-prompt]").forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.dataset.assistantPrompt || "";
        form.requestSubmit();
      });
    });
    $("assistantCloseButton").addEventListener("click", close);
    modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
    voiceControls = window.VarshaGuardVoice?.bind({
      button: $("assistantMicButton"),
      status: $("assistantVoiceStatus"),
      language: $("assistantVoiceLanguage"),
      input,
      sendButton: send,
      getContext: buildAssistantContext,
      appendMessage: appendAssistantMessage
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;
      appendAssistantMessage(question, "user");
      input.value = "";
      input.disabled = true;
      send.disabled = true;
      modal.dataset.assistantState = "thinking";
      window.VarshaGuardOrb?.setState("thinking");
      const orbLabel = $("assistantOrbState");
      if (orbLabel) orbLabel.textContent = "Thinking through the dashboard";
      const voiceButton = $("assistantMicButton");
      if (voiceButton) voiceButton.disabled = true;
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
        modal.dataset.assistantState = "idle";
        window.VarshaGuardOrb?.setState("idle");
        if (orbLabel) orbLabel.textContent = "Ready to help";
      } catch (error) {
        appendAssistantMessage(error.message, "error");
        modal.dataset.assistantState = "idle";
        window.VarshaGuardOrb?.setState("idle");
        if (orbLabel) orbLabel.textContent = "Ready to help";
      } finally {
        input.disabled = false;
        send.disabled = false;
        if (voiceButton) voiceButton.disabled = false;
        send.textContent = "Send";
        input.focus();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupMap();
    setupAssistant();
    $("districtSelect").addEventListener("change", () => selectDistrict());
    $("locateButton").addEventListener("click", useMyLocation);
    $("mapRefreshButton").addEventListener("click", () => selectDistrict());
    selectDistrict(false);
    loadDashboard();
    refreshTimer = window.setInterval(loadDashboard, REFRESH_MS);
    window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer), { once: true });
  });
})();
