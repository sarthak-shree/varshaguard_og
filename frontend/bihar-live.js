(() => {
  "use strict";

  const API = "/api/bihar-live/model/live";
  const DISTRICTS = {
    patna: { name: "Patna", center: [25.5941, 85.1376] },
    muzaffarpur: { name: "Muzaffarpur", center: [26.1209, 85.3647] }
  };
  const REFRESH_MS = 5 * 60 * 1000;
  const $ = (id) => document.getElementById(id);
  let map = null;
  let stationLayer = null;
  let userMarker = null;
  let currentData = {};
  let refreshTimer = null;

  async function getJson(path) {
    let response;
    try {
      response = await fetch(path, {
        cache: "no-store",
        headers: { Accept: "application/json" }
      });
    } catch {
      throw new Error("Could not connect to the Bihar Live API. Check the deployment and network connection.");
    }

    const contentType = response.headers.get("content-type") || "";
    const body = await response.text();
    let data;
    try {
      data = body ? JSON.parse(body) : {};
    } catch {
      const detail = response.status === 404
        ? "The API route was not found (404). The backend may not be deployed or the Vercel root directory may be misconfigured."
        : "The server returned HTML or invalid JSON instead of API data.";
      throw new Error("Bihar Live API error: " + detail);
    }

    if (!response.ok || data.success === false) {
      throw new Error(data.error || ("Bihar Live API request failed (" + response.status + ")."));
    }
    if (!contentType.includes("application/json") && typeof data !== "object") {
      throw new Error("Bihar Live API returned an unexpected response format.");
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

  function selectedPrediction() {
    const district = DISTRICTS[$("districtSelect").value];
    return (currentData.live?.predictions || []).find(
      (item) => item.district?.toLowerCase() === district.name.toLowerCase()
    ) || null;
  }

  function setRiskMeter(percent) {
    const meter = $("selectedRiskMeter");
    const fill = $("selectedRiskFill");
    const scale = $("selectedRiskScale");
    if (!finiteNumber(percent)) {
      meter.hidden = true;
      scale.hidden = true;
      meter.removeAttribute("aria-valuenow");
      meter.removeAttribute("aria-valuetext");
      fill.style.width = "0%";
      return;
    }
    const bounded = Math.max(0, Math.min(100, Number(percent)));
    meter.hidden = false;
    scale.hidden = false;
    meter.setAttribute("aria-valuenow", bounded.toFixed(1));
    meter.setAttribute("aria-valuetext", bounded.toFixed(1) + "% experimental chance of gauge warning-level crossing in 24 hours");
    fill.style.width = bounded + "%";
  }

  function updateSelectedRiskCard() {
    const districtKey = $("districtSelect").value;
    const district = DISTRICTS[districtKey];
    const prediction = selectedPrediction();
    const weather = currentData.weather?.[districtKey];
    const card = $("selectedRiskCard");
    const state = signalState(prediction);
    const observedWarning = prediction?.status === "warning_level_reached";
    const observedDanger = prediction?.status === "danger_level_reached";
    const probability = prediction?.status === "predicted" && finiteNumber(prediction.model_probability)
      ? (finiteNumber(prediction.risk_percentage) ? Number(prediction.risk_percentage) : Number(prediction.model_probability) * 100)
      : null;

    card.dataset.risk = state;
    card.dataset.state = prediction?.status || "unavailable";
    setText("selectedRiskDistrict", district.name);
    setText("selectedRiskGauge", prediction?.station_name ? "CWC gauge: " + prediction.station_name : "CWC gauge: awaiting a recent reading");
    setText("selectedRiskStage", finiteNumber(prediction?.current_stage_m) ? Number(prediction.current_stage_m).toFixed(2) + " m" : "—");
    setText("selectedRiskWarning", finiteNumber(prediction?.warning_level_m) ? Number(prediction.warning_level_m).toFixed(2) + " m" : "—");
    setText("selectedRiskDanger", finiteNumber(prediction?.danger_level_m) ? Number(prediction.danger_level_m).toFixed(2) + " m" : "—");
    setText("selectedRiskObservedRain", finiteNumber(prediction?.rainfall_24h_mm) ? Number(prediction.rainfall_24h_mm).toFixed(1) + " mm" : "—");
    setText("selectedRiskReadingTime", prediction?.observed_at_ist ? formatTime(prediction.observed_at_ist) : "Waiting");

    const badge = $("selectedRiskBadge");
    badge.dataset.state = state;
    if (observedDanger) badge.textContent = "DANGER OBSERVED";
    else if (observedWarning) badge.textContent = "WARNING OBSERVED";
    else if (prediction?.status === "predicted") badge.textContent = state.toUpperCase() + " MODEL RISK";
    else if (prediction?.status === "stale") badge.textContent = "STALE DATA";
    else if (prediction?.status === "insufficient_inputs") badge.textContent = "NOT ENOUGH DATA";
    else badge.textContent = "NO LIVE READING";

    if (finiteNumber(probability)) {
      setText("selectedRiskProbability", Number(probability).toFixed(1) + "%");
      setText("selectedRiskProbabilityLabel", "Chance this gauge reaches its CWC warning level within 24 hours");
      setRiskMeter(probability);
      setText("selectedRiskMessage", state.toUpperCase() + " estimate for " + district.name + " during the next 24 hours. This percentage is for its CWC gauge, not a neighborhood or block flood probability.");
    } else if (observedDanger || observedWarning) {
      setText("selectedRiskProbability", "Observed");
      setText("selectedRiskProbabilityLabel", observedDanger ? "CWC danger level already reached" : "CWC warning level already reached");
      setRiskMeter(null);
      setText("selectedRiskMessage", prediction.message || "A threshold has already been reached in the latest observation. This is not a forecast probability.");
    } else {
      setText("selectedRiskProbability", "—");
      setText("selectedRiskProbabilityLabel", "No current 24-hour estimate");
      setRiskMeter(null);
      setText("selectedRiskMessage", prediction?.message || currentData.live?.error || "Waiting for a fresh CWC reading. No risk percentage is shown until the required data are available.");
    }

    if (weather?.available && finiteNumber(weather.forecast_rainfall_24h_mm)) {
      const peakChance = finiteNumber(weather.peak_hourly_rainfall_probability_pct)
        ? " · peak hourly rain chance " + Math.round(Number(weather.peak_hourly_rainfall_probability_pct)) + "%"
        : "";
      setText("selectedRiskRainForecast", Number(weather.forecast_rainfall_24h_mm).toFixed(1) + " mm" + peakChance);
      setText("selectedRiskWeatherNote", "Open-Meteo weather-model outlook near the CWC gauge, refreshed " + formatTime(weather.fetched_at_ist) + ". It is shown as context and is not included in the flood-risk percentage.");
    } else {
      setText("selectedRiskRainForecast", weather ? "Unavailable" : "Loading");
      setText("selectedRiskWeatherNote", weather?.message || "Rainfall outlook is loading. It is separate from the CWC risk percentage.");
    }

    const coverage = prediction?.feature_coverage;
    const coverageText = coverage ? "Model inputs available: " + coverage.available + " of " + coverage.total + ". " : "";
    const ageText = finiteNumber(prediction?.data_age_hours) ? "Latest CWC reading " + hoursAgo(prediction.data_age_hours) + ". " : "";
    const localNote = prediction?.local_validation_note ? prediction.local_validation_note + " " : "";
    setText("selectedRiskQuality", coverageText + ageText + localNote + (prediction?.message && prediction.status !== "predicted" ? prediction.message : ""));
  }

  function renderSources(data, weather) {
    const source = data?.source || {};
    const root = $("sourceList");
    root.replaceChildren();
    const total = Number(source.stations_in_model) || 13;
    const entries = [
      { name: "CWC river stage (HHS)", count: source.stations_with_recent_stage },
      { name: "CWC rainfall (MPS)", count: source.stations_with_recent_rainfall },
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
    const weatherItem = document.createElement("div");
    weatherItem.className = "bihar-source-item";
    const weatherLabel = document.createElement("span");
    weatherLabel.textContent = "Open-Meteo rainfall forecast";
    const weatherStatus = document.createElement("strong");
    weatherStatus.textContent = weather?.available ? "available" : weather ? "unavailable" : "loading";
    weatherStatus.dataset.state = weather?.available ? "ready" : weather ? "unavailable" : "partial";
    weatherItem.append(weatherLabel, weatherStatus);
    root.appendChild(weatherItem);

    const cwcConnected = Boolean(data?.available);
    const subtitle = cwcConnected && weather?.available
      ? "CWC gauge observations and Open-Meteo weather context"
      : cwcConnected
        ? "CWC gauge readings are current; weather forecast is unavailable"
        : weather?.available
          ? "Rainfall forecast is available; CWC gauge estimate is offline"
          : "CWC gauge readings are not available right now";
    setText("sourceSubtitle", subtitle);
    setText("sourceCount", cwcConnected && weather?.available ? "3 FEEDS" : cwcConnected ? "CWC ONLY" : weather?.available ? "WEATHER ONLY" : "OFFLINE");
  }

  async function loadWeatherForecast(districtKey) {
    if (!DISTRICTS[districtKey]) return;
    const existing = currentData.weather?.[districtKey];
    if (existing?.fetched_at_ist) {
      const age = (Date.now() - new Date(existing.fetched_at_ist).getTime()) / 1000;
      if (Number.isFinite(age) && age >= 0 && age < 5 * 60) {
        if (districtKey === $("districtSelect").value) {
          updateSelectedRiskCard();
          renderSources(currentData.live || {}, existing);
        }
        return;
      }
    }
    currentData.weather ||= {};
    if (currentData.weatherLoading?.[districtKey]) return;
    currentData.weatherLoading ||= {};
    currentData.weatherLoading[districtKey] = true;
    if (districtKey === $("districtSelect").value) updateSelectedRiskCard();
    try {
      const result = await getJson("/api/bihar-live/weather?district=" + encodeURIComponent(districtKey));
      currentData.weather[districtKey] = result;
    } catch (error) {
      currentData.weather[districtKey] = { success: true, available: false, message: error.message };
    } finally {
      delete currentData.weatherLoading[districtKey];
      if (districtKey === $("districtSelect").value) {
        updateSelectedRiskCard();
        renderSources(currentData.live || {}, currentData.weather[districtKey]);
      }
    }
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
      signal.textContent = "HIGH · danger level reached (observed)";
    } else if (prediction.status === "warning_level_reached") {
      signal.textContent = "HIGH · warning level reached (observed)";
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
      const selected = prediction.district?.toLowerCase() === DISTRICTS[$("districtSelect").value].name.toLowerCase();
      const marker = L.circleMarker([lat, lon], {
        radius: selected ? 11 : 8, color: "#fff", weight: selected ? 3 : 2,
        fillColor: markerColor(prediction), fillOpacity: 1
      }).addTo(stationLayer).bindPopup(makePopup(prediction));
      marker.on("click", () => {
        const districtKey = Object.keys(DISTRICTS).find((key) => DISTRICTS[key].name.toLowerCase() === prediction.district?.toLowerCase());
        if (!districtKey) return;
        $("districtSelect").value = districtKey;
        selectDistrict(false);
        loadWeatherForecast(districtKey);
      });
    });
  }

  function updateDashboard(data) {
    currentData.live = data || {};
    const predictions = currentData.live.predictions || [];
    renderMap(predictions);
    updateSelectedRiskCard();
    renderSources(currentData.live, currentData.weather?.[$("districtSelect").value]);
    selectDistrict(false);
    clearError();
  }

  async function loadDashboard() {
    try {
      const data = await getJson(API);
      updateDashboard(data);
      loadWeatherForecast($("districtSelect").value);
      if (!data.available) showError(data.error || "CWC live data is currently unavailable.");
    } catch (error) {
      showError(error.message);
      currentData.live = {
        available: false,
        error: "No current estimate is shown because the CWC service could not be reached.",
        predictions: [],
      };
      renderMap([]);
      updateSelectedRiskCard();
      renderSources(currentData.live, currentData.weather?.[$("districtSelect").value]);
      loadWeatherForecast($("districtSelect").value);
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
    updateSelectedRiskCard();
    renderMap(currentData.live?.predictions || []);
    renderSources(currentData.live || {}, currentData.weather?.[$("districtSelect").value]);
    if (moveMap && map) {
      const prediction = selectedPrediction();
      const center = prediction && finiteNumber(prediction.latitude)
        ? [Number(prediction.latitude), Number(prediction.longitude)] : district.center;
      map.setView(center, 10, { animate: true });
    }
    const assistantInput = $("assistantInput");
    if (assistantInput) assistantInput.placeholder = "Ask about " + district.name + " river readings";
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
        const distanceKm = (a, b) => {
          const rad = (value) => value * Math.PI / 180;
          const latDelta = rad(b[0] - a[0]);
          const lonDelta = rad(b[1] - a[1]);
          const haversine = Math.sin(latDelta / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(lonDelta / 2) ** 2;
          return 6371 * 2 * Math.asin(Math.sqrt(haversine));
        };
        const nearest = Object.entries(DISTRICTS)
          .map(([key, district]) => ({ key, district, distance: distanceKm(point, district.center) }))
          .sort((a, b) => a.distance - b.distance)[0];
        if (nearest && nearest.distance <= 40) {
          $("districtSelect").value = nearest.key;
          selectDistrict(false);
          loadWeatherForecast(nearest.key);
          map.setView(point, 11, { animate: true });
          clearError();
        } else {
          map.setView(point, 9, { animate: true });
          showError("Your location is outside the supported Patna and Muzaffarpur gauge areas. Choose a focus district to see its gauge estimate.");
        }
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
      selected_rain_forecast: currentData.weather?.[$("districtSelect").value] || "unavailable",
      all_gauges: predictions,
      model_scope: currentData.live?.target_definition || "unavailable",
      risk_bands: currentData.live?.risk_bands || "unavailable",
      limitations: currentData.live?.limitations || ["No current data is available."],
      instruction: "Answer for the selected location only. The experimental percentage estimates whether the selected CWC gauge reaches its published warning level within 24 hours; it is not a block or street flood probability and is not an official warning. Show the Open-Meteo rain forecast as separate context only; it is not included in the CWC model percentage. Muzaffarpur has too few local holdout events to estimate local accuracy. If readings are stale or inputs are insufficient, say no current estimate is available."
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
      const modal = document.getElementById("assistantModal");
      const openButtons = [
          document.getElementById("assistantOpenButton"),
          document.getElementById("assistantTopButton"),
          document.querySelector(".ai-hero-card .ai-orb"),
      ].filter(Boolean);
      const closeButton = document.getElementById("assistantCloseButton");
      const form = document.getElementById("assistantForm");
      const input = document.getElementById("assistantInput");
      const sendButton = document.getElementById("assistantSendButton");
      const textModeButton = document.getElementById("assistantTextMode");
      const voiceModeButton = document.getElementById("assistantVoiceMode");
      const orbPanel = document.getElementById("assistantOrbPanel");
      const voiceRow = document.getElementById("assistantVoiceRow");
      let voiceControls = null;
      let returnFocus = null;

      if (!modal || !openButtons.length || !closeButton || !form || !input || !sendButton) return;

      const setAssistantMode = (mode) => {
          const voiceMode = mode === "voice";
          modal.dataset.assistantMode = voiceMode ? "voice" : "text";
          orbPanel?.classList.toggle("hidden", !voiceMode);
          voiceRow?.classList.toggle("hidden", !voiceMode);
          textModeButton?.classList.toggle("is-active", !voiceMode);
          voiceModeButton?.classList.toggle("is-active", voiceMode);
          textModeButton?.setAttribute("aria-pressed", String(!voiceMode));
          voiceModeButton?.setAttribute("aria-pressed", String(voiceMode));
          if (voiceMode) {
              window.VarshaGuardOrb?.setState("idle");
              const status = document.getElementById("assistantVoiceStatus");
              if (status) status.textContent = "Tap Speak when you're ready.";
          } else {
              voiceControls?.cancel();
              window.VarshaGuardOrb?.setState("idle");
              input.focus();
          }
      };

      textModeButton?.addEventListener("click", () => setAssistantMode("text"));
      voiceModeButton?.addEventListener("click", () => setAssistantMode("voice"));

      const open = () => {
          returnFocus = document.activeElement;
          // Use the current Bihar Live context when a question is submitted.
          modal.classList.remove("hidden");
          setAssistantMode("text");
          window.VarshaGuardOrb?.setState("idle");
          input.focus();
      };
      const close = () => {
          voiceControls?.cancel();
          modal.classList.add("hidden");
          modal.dataset.assistantMode = "text";
          window.VarshaGuardOrb?.setState("idle");
          returnFocus?.focus();
          returnFocus = null;
      };

      openButtons.forEach((button) => button.addEventListener("click", open));
      document.querySelectorAll("[data-assistant-prompt]").forEach((button) => {
          button.addEventListener("click", () => {
              input.value = button.dataset.assistantPrompt || "";
              form.requestSubmit();
          });
      });
      closeButton.addEventListener("click", close);
      modal.addEventListener("click", (event) => {
          if (event.target === modal) close();
      });
      document.addEventListener("keydown", (event) => {
          if (event.key === "Escape") close();
      });

      document.addEventListener("keydown", (event) => {
          if (modal.classList.contains("hidden") || event.key !== "Tab") return;
          const focusable = Array.from(modal.querySelectorAll(
              'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), audio[controls], a[href], [tabindex]:not([tabindex="-1"])'
          )).filter((element) => !element.closest(".hidden") && element.getClientRects().length > 0);
          if (!focusable.length) {
              event.preventDefault();
              return;
          }
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === modal)) {
              event.preventDefault();
              last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
          }
      });

      voiceControls = window.VarshaGuardVoice?.bind({
          button: document.getElementById("assistantMicButton"),
          status: document.getElementById("assistantVoiceStatus"),
          language: document.getElementById("assistantVoiceLanguage"),
          input,
          sendButton,
          getContext: buildAssistantContext,
          appendMessage: appendAssistantMessage,
      });

      const nativeOrb = document.getElementById("assistantNativeOrb");
      nativeOrb?.addEventListener("click", () => {
          if (modal.dataset.assistantMode === "voice") voiceControls?.toggle();
      });


      form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const question = input.value.trim();
          if (!question) return;

          appendAssistantMessage(question, "user");
          input.value = "";
          input.disabled = true;
          sendButton.disabled = true;
          modal.dataset.assistantState = "thinking";
          window.VarshaGuardOrb?.setState("thinking");
          const orbLabel = document.getElementById("assistantOrbState");
          if (orbLabel) orbLabel.textContent = "Thinking through the dashboard";
          const voiceButton = document.getElementById("assistantMicButton");
          if (voiceButton) voiceButton.disabled = true;
          sendButton.textContent = "Thinking…";

          try {
              const context = buildAssistantContext();
              const response = await fetch("/api/assistant", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ message: question, context }),
              });
              const data = await response.json();
              if (!response.ok || data.success === false) {
                  throw new Error(data.error || "Assistant request failed");
              }
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
              sendButton.disabled = false;
              if (voiceButton) voiceButton.disabled = false;
              sendButton.textContent = "Send";
              input.focus();
          }
      });
  }
  document.addEventListener("DOMContentLoaded", () => {
    const gaugeDetails = document.querySelectorAll(".live-gauge-details");
    const compactGaugeCards = window.matchMedia("(max-width: 620px)");
    const setGaugeDetails = (compact) => gaugeDetails.forEach((details) => { details.open = !compact; });
    setGaugeDetails(compactGaugeCards.matches);
    compactGaugeCards.addEventListener("change", (event) => setGaugeDetails(event.matches));
    setupMap();
    setupAssistant();
    $("districtSelect").addEventListener("change", () => {
      selectDistrict();
      loadWeatherForecast($("districtSelect").value);
    });
    $("locateButton").addEventListener("click", useMyLocation);
    $("mapRefreshButton").addEventListener("click", () => selectDistrict());
    selectDistrict(false);
    loadDashboard();
    refreshTimer = window.setInterval(loadDashboard, REFRESH_MS);
    window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer), { once: true });
  });
})();
