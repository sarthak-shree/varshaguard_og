(() => {
  "use strict";

  const API = "/api/bihar-live/model/live";
  const DISTRICTS = {
    patna: { name: "Patna", center: [25.5941, 85.1376] },
    muzaffarpur: { name: "Muzaffarpur", center: [26.1209, 85.3647] }
  };
  const REFRESH_MS = 5 * 60 * 1000;
  const $ = (id) => document.getElementById(id);
  const t = (key, fallback, values = {}) => String(fallback ?? key).replace(/\{(\w+)\}/g, (_, name) => values[name] == null ? "" : String(values[name]));
  const locale = () => "en-IN";
  const riskWord = (state) => state.charAt(0).toUpperCase() + state.slice(1);
  const districtLabel = (name) => name;
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
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString(locale(), {
      day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata"
    });
  }

  function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value.includes("+") || value.endsWith("Z") ? value : value + "+05:30");
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleString(locale(), {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata"
    }) + " IST";
  }

  function hoursAgo(value) {
    const hours = Number(value);
    if (!finiteNumber(value)) return t("ageUnknown", "age unknown");
    if (hours < 1) return t("lessHour", "less than 1 hour ago");
    return t("hoursAgo", hours === 1 ? "{hours} hour ago" : "{hours} hours ago", { hours: Math.round(hours) });
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
    if (!meter || !fill || !scale) return;
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
    meter.setAttribute("aria-valuetext", bounded.toFixed(1) + "% " + t("gaugeWarningAria", "experimental chance of gauge warning-level crossing in 24 hours"));
    fill.style.width = bounded + "%";
  }

  function renderStageTrend(prediction) {
    const svg = $("stageTrendSvg");
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const points = (prediction?.stage_history || [])
      .filter((item) => finiteNumber(item.stage_m) && item.timestamp_ist)
      .map((item) => {
        const rawTime = String(item.timestamp_ist);
        const parsed = new Date(rawTime.includes("+") || rawTime.endsWith("Z") ? rawTime : rawTime + "+05:30");
        return { time: parsed.getTime(), stage: Number(item.stage_m), rawTime };
      })
      .filter((item) => Number.isFinite(item.time))
      .sort((a, b) => a.time - b.time);

    const warning = finiteNumber(prediction?.warning_level_m) ? Number(prediction.warning_level_m) : null;
    const count = $("stageTrendCount");
    const summary = $("stageTrendSummary");
    const width = 600;
    const height = 220;
    const pad = { left: 54, right: 18, top: 24, bottom: 34 };
    const make = (name, attrs = {}, content = "") => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (content) node.textContent = content;
      return node;
    };

    if (!points.length) {
      count.textContent = t("noReadings", "No readings");
      summary.textContent = t("noTrend", "A river-level trend will appear when recent CWC readings are available.");
      svg.setAttribute("aria-label", summary.textContent);
      svg.appendChild(make("text", { class: "stage-trend-empty", x: 300, y: 110, "text-anchor": "middle" }, t("noRecentReadings", "No recent river readings available")));
      return;
    }

    const observed = points.map((point) => point.stage);
    const minValue = Math.min(...observed);
    const maxValue = Math.max(...observed);
    const spread = Math.max(0.2, maxValue - minValue);
    let low = minValue - spread * 0.25;
    let high = maxValue + spread * 0.25;
    if (warning !== null && warning >= low && warning <= high) {
      low = Math.min(low, warning - spread * 0.05);
      high = Math.max(high, warning + spread * 0.05);
    }
    const x0 = pad.left;
    const x1 = width - pad.right;
    const y0 = pad.top;
    const y1 = height - pad.bottom;
    const firstTime = points[0].time;
    const lastTime = points[points.length - 1].time;
    const timeSpan = Math.max(1, lastTime - firstTime);
    const x = (point, index) => points.length === 1 ? (x0 + x1) / 2 : x0 + ((point.time - firstTime) / timeSpan) * (x1 - x0);
    const y = (value) => y1 - ((value - low) / (high - low)) * (y1 - y0);

    for (let tick = 0; tick <= 2; tick += 1) {
      const value = high - ((high - low) * tick / 2);
      const yy = y(value);
      svg.appendChild(make("line", { class: "stage-trend-grid", x1: x0, x2: x1, y1: yy, y2: yy }));
      svg.appendChild(make("text", { class: "stage-trend-axis-label", x: x0 - 8, y: yy + 4, "text-anchor": "end" }, value.toFixed(1) + " m"));
    }

    if (warning !== null && warning >= low && warning <= high) {
      const warningY = y(warning);
      svg.appendChild(make("line", { class: "stage-trend-warning", x1: x0, x2: x1, y1: warningY, y2: warningY }));
      svg.appendChild(make("text", { class: "stage-trend-warning-label", x: x1 - 2, y: Math.max(y0 + 10, warningY - 7), "text-anchor": "end" }, t("warningMark", "WARNING {level} m", { level: warning.toFixed(2) })));
    } else if (warning !== null) {
      const latestStage = points[points.length - 1].stage;
      const relation = warning > latestStage ? t("above", "above") : t("below", "below");
      const gap = Math.abs(warning - latestStage).toFixed(2);
      const labelY = warning > latestStage ? y0 + 11 : y1 - 6;
      svg.appendChild(make("text", { class: "stage-trend-warning-label", x: x1 - 2, y: labelY, "text-anchor": "end" }, t("warningGapChart", "WARNING LINE {gap} m {relation} latest", { gap, relation })));
    }

    let segment = [];
    const drawSegment = () => {
      if (segment.length > 1) {
        const path = segment.map((point, index) => (index ? "L" : "M") + " " + x(point, points.indexOf(point)).toFixed(1) + " " + y(point.stage).toFixed(1)).join(" ");
        svg.appendChild(make("path", { class: "stage-trend-line", d: path }));
      }
    };
    points.forEach((point, index) => {
      if (index && point.time - points[index - 1].time > 4 * 60 * 60 * 1000) {
        drawSegment();
        segment = [];
      }
      segment.push(point);
    });
    drawSegment();

    points.forEach((point, index) => {
      const circle = make("circle", {
        class: index === points.length - 1 ? "stage-trend-point is-latest" : "stage-trend-point",
        cx: x(point, index),
        cy: y(point.stage),
        r: index === points.length - 1 ? 5 : 3
      });
      circle.appendChild(make("title", {}, formatTime(point.rawTime) + " · " + point.stage.toFixed(2) + " m"));
      svg.appendChild(circle);
    });

    svg.appendChild(make("text", { class: "stage-trend-axis-label", x: x0, y: height - 8, "text-anchor": "start" }, t("earlier", "Earlier")));
    svg.appendChild(make("text", { class: "stage-trend-axis-label", x: x1, y: height - 8, "text-anchor": "end" }, t("latest", "Latest")));
    count.textContent = t("countReadings", points.length === 1 ? "{count} reading" : "{count} readings", { count: points.length });

    const change = points[points.length - 1].stage - points[0].stage;
    const spanHours = Math.max(0, (lastTime - firstTime) / 3600000);
    const amount = Math.abs(change).toFixed(2);
    const direction = Math.abs(change) < 0.03 ? t("stayedSame", "stayed about the same") : change > 0 ? t("roseBy", "rose by {amount} m", { amount }) : t("fellBy", "fell by {amount} m", { amount });
    summary.textContent = points.length < 2
      ? t("onlyOneReading", "Only one recent reading is available, so a trend cannot be shown.")
      : t("trendSummary", "The level {direction} over {hours} observed hours. This chart uses CWC readings, not predicted future river levels.", { direction, hours: spanHours < 1 ? t("observedPeriod", "the observed period") : spanHours.toFixed(0) });
    svg.setAttribute("aria-label", t("trendAria", "Recent observed river-level trend. ") + summary.textContent);
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

    if (card) {
      card.dataset.risk = state;
      card.dataset.state = prediction?.status || "unavailable";
    }
    renderStageTrend(prediction);
    setText("selectedRiskDistrict", districtLabel(district.name));
    setText("selectedRiskGauge", prediction?.station_name ? t("gaugeNamed", "CWC gauge: {name}", { name: prediction.station_name }) : t("gaugeAwaiting", "CWC gauge: awaiting a recent reading"));
    setText("selectedRiskWindow", prediction?.forecast_end_ist
      ? t("nextWindow", "Next 24 hours · through {time}", { time: formatTime(prediction.forecast_end_ist) })
      : t("nextAfterReading", "Next 24 hours after the latest CWC reading"));
    setText("selectedRiskStage", finiteNumber(prediction?.current_stage_m) ? Number(prediction.current_stage_m).toFixed(2) + " m" : "—");
    setText("selectedRiskGap", finiteNumber(prediction?.margin_to_warning_m)
      ? t(Number(prediction.margin_to_warning_m) < 0 ? "distanceAbove" : "distanceBelow", "{amount} m " + (Number(prediction.margin_to_warning_m) < 0 ? "above" : "below"), { amount: Math.abs(Number(prediction.margin_to_warning_m)).toFixed(2) })
      : "—");
    setText("selectedRiskWarning", finiteNumber(prediction?.warning_level_m) ? Number(prediction.warning_level_m).toFixed(2) + " m" : "—");
    setText("selectedRiskDanger", finiteNumber(prediction?.danger_level_m) ? Number(prediction.danger_level_m).toFixed(2) + " m" : "—");
    setText("selectedRiskObservedRain", finiteNumber(prediction?.rainfall_24h_mm) ? Number(prediction.rainfall_24h_mm).toFixed(1) + " mm" : "—");
    setText("selectedRiskReadingTime", prediction?.observed_at_ist ? formatTime(prediction.observed_at_ist) : t("loading", "Waiting"));

    const coverage = prediction?.feature_coverage;
    setText("selectedRiskFreshness", prediction?.observed_at_ist
      ? t("latestReading", "Latest CWC reading: {time} ({age})", { time: formatTime(prediction.observed_at_ist), age: hoursAgo(prediction.data_age_hours) })
      : t("freshnessWaiting", "Latest CWC reading: waiting for data"));
    setText("selectedRiskCoverage", coverage && finiteNumber(coverage.available) && finiteNumber(coverage.total)
      ? t("inputCoverage", "Model inputs available: {available} of {total}", { available: coverage.available, total: coverage.total })
      : t("coverageWaiting", "Model input coverage: waiting for data"));

    const badge = $("selectedRiskBadge");
    if (badge) {
      badge.dataset.state = state;
      if (observedDanger) badge.textContent = "▲ " + t("badgeDanger", "DANGER OBSERVED");
      else if (observedWarning) badge.textContent = "▲ " + t("badgeWarning", "WARNING OBSERVED");
      else if (prediction?.status === "predicted") badge.textContent = (state === "low" ? "✓ " : state === "medium" ? "◆ " : "▲ ") + t("badgeModel", "{risk} MODEL RISK", { risk: riskWord(state).toUpperCase() });
      else if (prediction?.status === "stale") badge.textContent = "◷ " + t("badgeStale", "STALE DATA");
      else if (prediction?.status === "insufficient_inputs") badge.textContent = "• " + t("badgeInsufficient", "NOT ENOUGH DATA");
      else badge.textContent = "— " + t("badgeUnavailable", "NO LIVE READING");
    }

    if (finiteNumber(probability)) {
      setText("selectedRiskProbability", Number(probability).toFixed(1) + "%");
      setText("selectedRiskProbabilityLabel", t("chanceWarning", "Chance this gauge reaches the CWC warning line in the next 24 hours"));
      setRiskMeter(probability);
      setText("selectedRiskMessage", t("riskMessage", "{risk} model estimate for this gauge over the next 24 hours. It is not a street or home flood probability.", { risk: riskWord(state) }));
    } else if (observedDanger || observedWarning) {
      setText("selectedRiskProbability", t("observed", "Observed"));
      setText("selectedRiskProbabilityLabel", observedDanger ? t("observedDanger", "The gauge is already at its CWC danger line") : t("observedWarning", "The gauge is already at its CWC warning line"));
      setRiskMeter(null);
      setText("selectedRiskMessage", prediction.message || t("thresholdReached", "A threshold has already been reached in the latest observation. This is not a forecast probability."));
    } else {
      setText("selectedRiskProbability", "—");
      setText("selectedRiskProbabilityLabel", t("noCurrentEstimate", "No current 24-hour estimate"));
      setRiskMeter(null);
      setText("selectedRiskMessage", prediction?.message || currentData.live?.error || t("waitingEstimate", "Waiting for a fresh CWC reading. No risk percentage is shown until the required data are available."));
    }

    if (weather?.available && finiteNumber(weather.forecast_rainfall_24h_mm)) {
      const peakChance = finiteNumber(weather.peak_hourly_rainfall_probability_pct)
        ? t("rainChance", " · peak hourly rain chance {chance}%", { chance: Math.round(Number(weather.peak_hourly_rainfall_probability_pct)) })
        : "";
      setText("selectedRiskRainForecast", Number(weather.forecast_rainfall_24h_mm).toFixed(1) + " mm" + peakChance);
      setText("selectedRiskWeatherNote", t("weatherNote", "Open-Meteo weather-model outlook near the CWC gauge, refreshed {time}. It is shown as context and is not included in the flood-risk percentage.", { time: formatTime(weather.fetched_at_ist) }));
    } else {
      setText("selectedRiskRainForecast", weather ? t("rainUnavailable", "Unavailable") : t("rainLoading", "Loading"));
      setText("selectedRiskWeatherNote", weather?.message || t("rainLoadingNote", "Rainfall outlook is loading. It is separate from the CWC risk percentage."));
    }

    const coverageText = coverage ? t("qualityCoverage", "Model inputs available: {available} of {total}. ", { available: coverage.available, total: coverage.total }) : "";
    const ageText = finiteNumber(prediction?.data_age_hours) ? t("qualityAge", "Latest CWC reading {age}. ", { age: hoursAgo(prediction.data_age_hours) }) : "";
    const localNote = prediction?.local_validation_note ? prediction.local_validation_note + " " : "";
    setText("selectedRiskQuality", coverageText + ageText + localNote + (prediction?.message && prediction.status !== "predicted" ? prediction.message : "") || t("qualityWaiting", "Waiting for data quality details."));
  }

  function renderSources(data, weather) {
    const source = data?.source || {};
    const root = $("sourceList");
    root.replaceChildren();
    const total = Number(source.stations_in_model) || 13;
    const entries = [
      { name: t("sourceStage", "CWC river stage (HHS)"), count: source.stations_with_recent_stage },
      { name: t("sourceRain", "CWC rainfall (MPS)"), count: source.stations_with_recent_rainfall },
    ];
    entries.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "bihar-source-item";
      const label = document.createElement("span");
      label.textContent = entry.name;
      const status = document.createElement("strong");
      const count = Number(entry.count);
      status.textContent = finiteNumber(entry.count) ? count + "/" + total + " " + t("gauges", "gauges") : t("unavailable", "unavailable");
      status.dataset.state = finiteNumber(entry.count) && count > 0 ? (count === total ? "ready" : "partial") : "unavailable";
      item.append(label, status);
      root.appendChild(item);
    });
    const weatherItem = document.createElement("div");
    weatherItem.className = "bihar-source-item";
    const weatherLabel = document.createElement("span");
    weatherLabel.textContent = t("sourceForecast", "Open-Meteo rainfall forecast");
    const weatherStatus = document.createElement("strong");
    weatherStatus.textContent = weather?.available ? t("available", "available") : weather ? t("unavailable", "unavailable") : t("loading", "loading");
    weatherStatus.dataset.state = weather?.available ? "ready" : weather ? "unavailable" : "partial";
    weatherItem.append(weatherLabel, weatherStatus);
    root.appendChild(weatherItem);

    const cwcConnected = Boolean(data?.available);
    const subtitle = cwcConnected && weather?.available
      ? t("cwcWeatherBoth", "CWC gauge observations and Open-Meteo weather context")
      : cwcConnected
        ? t("cwcOnly", "CWC gauge readings are current; weather forecast is unavailable")
        : weather?.available
          ? t("weatherOnly", "Rainfall forecast is available; CWC gauge estimate is offline")
          : t("sourcesOffline", "CWC gauge readings are not available right now");
    setText("sourceSubtitle", subtitle);
    setText("sourceCount", cwcConnected && weather?.available ? t("threeFeeds", "3 FEEDS") : cwcConnected ? t("cwcFeed", "CWC ONLY") : weather?.available ? t("weatherFeed", "WEATHER ONLY") : t("offline", "OFFLINE"));
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
  function renderForecastOutlook(districtKey) {
    const rain = currentData.rainForecast?.[districtKey];
    const stage = currentData.stageForecast?.[districtKey];
    const amounts = rain?.rainfall_accumulation_mm || {};
    const fmtRain = (key) => finiteNumber(amounts[key]) ? Number(amounts[key]).toFixed(1) + " mm" : "—";
    setText("forecastRain1h", fmtRain("next_1h"));
    setText("forecastRain3h", fmtRain("next_3h"));
    setText("forecastRain6h", fmtRain("next_6h"));
    setText("forecastRain24h", fmtRain("next_24h"));
    setText("rainForecastFreshness", rain?.fetched_at_ist
      ? "Fetched " + formatTime(rain.fetched_at_ist) + (finiteNumber(rain.cache_age_seconds) ? " · cached " + Math.round(Number(rain.cache_age_seconds)) + "s" : "")
      : rain?.available ? "Provider forecast available" : "Forecast unavailable");
    setText("rainForecastNote", rain?.available
      ? "Open-Meteo provider NWP forecast. Local independent rain-gauge validation is not yet available; this is not a heavy-rain or flood probability."
      : (rain?.message || "Waiting for a valid hourly rainfall forecast."));
    setText("stageForecastFreshness", stage?.source_observed_at_ist
      ? "CWC observation " + formatTime(stage.source_observed_at_ist) +
        (finiteNumber(stage.source_data_age_hours) ? " · " + Number(stage.source_data_age_hours).toFixed(1) + "h old" : "")
      : "Waiting for gauge history");
    setText("stageForecastDirection", stage?.available
      ? (stage.trend_direction === "rising" ? "↑ Rising trend" : stage.trend_direction === "falling" ? "↓ Falling trend" : "→ Nearly steady")
      : "Forecast unavailable");
    const values = $("stageForecastValues");
    if (values) {
      values.replaceChildren();
      if (stage?.available && Array.isArray(stage.forecasts)) {
        stage.forecasts.forEach((item) => {
          const cell = document.createElement("div");
          cell.className = "forecast-stage-value";
          const label = document.createElement("span");
          label.textContent = "+" + item.horizon_hours + " hours";
          const value = document.createElement("strong");
          value.textContent = finiteNumber(item.projected_stage_m) ? Number(item.projected_stage_m).toFixed(2) + " m" : "—";
          cell.append(label, value);
          values.appendChild(cell);
        });
      } else {
        values.textContent = stage?.message || "Not enough recent CWC readings for a trend baseline.";
      }
    }
    setText("stageForecastNote", stage?.available
      ? "Unvalidated linear extrapolation from recent CWC readings; not a trained ML model or confidence interval. Rainfall and upstream changes can invalidate the trend."
      : "The stage baseline needs at least three distinct readings spanning two hours. No forecast is invented when data are insufficient.");
    const status = $("forecastOutlookStatus");
    if (status) status.textContent = rain?.available && stage?.available ? "Both sources" :
      rain?.available ? "Rainfall only" : stage?.available ? "CWC only" : "Waiting";
  }

  async function loadForecastOutlook(districtKey) {
    if (!DISTRICTS[districtKey]) return;
    currentData.rainForecast ||= {};
    currentData.stageForecast ||= {};
    currentData.forecastLoading ||= {};
    if (currentData.forecastLoading[districtKey]) return;
    currentData.forecastLoading[districtKey] = true;
    try {
      const [rain, stage] = await Promise.allSettled([
        getJson("/api/bihar-live/forecast/rainfall?district=" + encodeURIComponent(districtKey)),
        getJson("/api/bihar-live/forecast/river-stage?district=" + encodeURIComponent(districtKey))
      ]);
      currentData.rainForecast[districtKey] = rain.status === "fulfilled"
        ? rain.value : { available: false, message: rain.reason?.message || "Rainfall forecast unavailable." };
      currentData.stageForecast[districtKey] = stage.status === "fulfilled"
        ? stage.value : { available: false, message: stage.reason?.message || "River-stage forecast unavailable." };
    } finally {
      delete currentData.forecastLoading[districtKey];
      if (districtKey === $("districtSelect").value) renderForecastOutlook(districtKey);
    }
  }

  function renderDischargeContext(districtKey) {
    const prediction = (currentData.live?.predictions || []).find(
      (item) => String(item.district || "").toLowerCase() === String(DISTRICTS[districtKey]?.name || "").toLowerCase()
    );
    const history = (prediction?.stage_history || [])
      .filter((item) => finiteNumber(item.stage_m) && item.timestamp_ist)
      .map((item) => ({ value: Number(item.stage_m), time: String(item.timestamp_ist) }))
      .sort((a, b) => new Date(a.time) - new Date(b.time));
    const stageValues = history.map((item) => item.value);
    const stageAverage = stageValues.length >= 2
      ? stageValues.reduce((sum, value) => sum + value, 0) / stageValues.length
      : null;
    setText("cwcAverageStage", stageAverage === null ? "—" : stageAverage.toFixed(2) + " m");
    setText("cwcStageWindow", history.length >= 2
      ? history.length + " quality-checked readings in the latest 24-hour history"
      : "Not enough recent CWC readings to calculate an average");
    const stageChange = history.length >= 2 ? history[history.length - 1].value - history[0].value : null;
    setText("cwcStageTrend", stageChange === null ? "Trend: insufficient observations" :
      "Observed change: " + (stageChange > 0.02 ? "rose " : stageChange < -0.02 ? "fell " : "was nearly steady ") +
      (Math.abs(stageChange) < 0.03 ? "" : Math.abs(stageChange).toFixed(2) + " m") + " across the available readings");

    const discharge = currentData.discharge?.[districtKey];
    const daily = discharge?.daily || {};
    const times = Array.isArray(daily.time) ? daily.time : [];
    const values = Array.isArray(daily.river_discharge_mean) ? daily.river_discharge_mean
      : Array.isArray(daily.river_discharge) ? daily.river_discharge : [];
    const today = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit"
    }).format(new Date());
    const forecastValues = times.map((day, index) => ({ day, value: values[index] }))
      .filter((item) => item.day >= today && finiteNumber(item.value));
    const dischargeAverage = forecastValues.length
      ? forecastValues.reduce((sum, item) => sum + Number(item.value), 0) / forecastValues.length
      : null;
    const units = discharge?.units || {};
    const unit = units.river_discharge_mean || units.river_discharge || "provider units";
    setText("openMeteoAverageDischarge", dischargeAverage === null ? "—" : dischargeAverage.toFixed(1) + " " + unit);
    setText("openMeteoDischargeWindow", forecastValues.length
      ? "Mean of " + forecastValues.length + " daily " + (units.river_discharge_mean ? "mean" : "discharge") + " values from today onward"
      : (discharge?.message || "No numeric Open-Meteo discharge forecast is available"));
    const dischargeChange = forecastValues.length >= 2
      ? Number(forecastValues[forecastValues.length - 1].value) - Number(forecastValues[0].value) : null;
    setText("openMeteoDischargeTrend", dischargeChange === null ? "Trend: insufficient forecast values" :
      "Forecast change: " + (dischargeChange > 0 ? "rising " : dischargeChange < 0 ? "falling " : "nearly steady ") +
      (Math.abs(dischargeChange) < 0.001 ? "" : Math.abs(dischargeChange).toFixed(1) + " " + unit) + " from first to last displayed day");
    const status = $("dischargeContextStatus");
    if (status) status.textContent = stageAverage !== null && dischargeAverage !== null ? "Both sources" :
      stageAverage !== null ? "CWC only" : dischargeAverage !== null ? "Open-Meteo only" : "Waiting";
    setText("dischargeContextNote", "CWC average: " + (stageAverage === null ? "not available" : stageAverage.toFixed(2) + " m") +
      ". Open-Meteo average discharge: " + (dischargeAverage === null ? "not available" : dischargeAverage.toFixed(1) + " " + unit) +
      ". These are separate averages, not a combined number: metres of river stage and discharge flow are different physical quantities. Patna and Muzaffarpur are displayed as separate focus gauges, not assumed to be an upstream/downstream pair. The existing ML model estimates CWC warning-level crossing from gauge history and rainfall features; it is not trained to convert discharge into stage.");
  }

  async function loadDischargeContext(districtKey) {
    if (!DISTRICTS[districtKey]) return;
    currentData.discharge ||= {};
    const existing = currentData.discharge[districtKey];
    if (existing?.fetched_at_utc) {
      const age = (Date.now() - new Date(existing.fetched_at_utc).getTime()) / 1000;
      if (Number.isFinite(age) && age >= 0 && age < 15 * 60) {
        if (districtKey === $("districtSelect").value) renderDischargeContext(districtKey);
        return;
      }
    }
    currentData.dischargeLoading ||= {};
    if (currentData.dischargeLoading[districtKey]) return;
    currentData.dischargeLoading[districtKey] = true;
    try {
      currentData.discharge[districtKey] = await getJson("/api/bihar-live/flood-discharge?district=" + encodeURIComponent(districtKey));
      currentData.discharge[districtKey].fetched_at_utc ||= new Date().toISOString();
    } catch (error) {
      currentData.discharge[districtKey] = { available: false, message: error.message };
    } finally {
      delete currentData.dischargeLoading[districtKey];
      if (districtKey === $("districtSelect").value) renderDischargeContext(districtKey);
    }
  }

  function makePopup(prediction) {
    const root = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = prediction.district + " · " + prediction.station_name;
    const reading = document.createElement("div");
    reading.textContent = finiteNumber(prediction.current_stage_m)
      ? t("latestLevel", "Latest level: {level} m", { level: Number(prediction.current_stage_m).toFixed(2) })
      : t("latestLevelUnavailable", "Latest level unavailable");
    const signal = document.createElement("div");
    if (prediction.status === "predicted") {
      const percent = finiteNumber(prediction.risk_percentage)
        ? Number(prediction.risk_percentage)
        : Number(prediction.model_probability) * 100;
      const riskLabel = (prediction.risk_level || "model").toUpperCase();
      signal.textContent = t("crossingChance", "{risk} risk · {percent}% chance of warning-level crossing in 24h", { risk: riskWord(prediction.risk_level || "medium").toUpperCase(), percent: percent.toFixed(1) });
    } else if (prediction.status === "danger_level_reached") {
      signal.textContent = t("highDanger", "HIGH · danger level reached (observed)");
    } else if (prediction.status === "warning_level_reached") {
      signal.textContent = t("highWarning", "HIGH · warning level reached (observed)");
    } else {
      signal.textContent = prediction.signal || prediction.message || t("noEstimate", "No current model estimate");
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
        showMapGaugeDetails(prediction);
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
    renderDischargeContext($("districtSelect").value);
    selectDistrict(false);
    clearError();
  }

  async function loadDashboard() {
    try {
      const data = await getJson(API);
      updateDashboard(data);
      loadWeatherForecast($("districtSelect").value);
      loadDischargeContext($("districtSelect").value);
      loadForecastOutlook($("districtSelect").value);
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
      loadDischargeContext($("districtSelect").value);
      loadForecastOutlook($("districtSelect").value);
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
    if (assistantInput) assistantInput.placeholder = t("askDistrict", "Ask about {district} river readings", { district: districtLabel(district.name) });
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      showError(t("locationUnavailable", "Location access is not available in this browser."));
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
        userMarker.bindPopup(t("myLocation", "Your current location")).openPopup();
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
          loadDischargeContext(nearest.key);
          loadForecastOutlook(nearest.key);
          map.setView(point, 11, { animate: true });
          clearError();
        } else {
          map.setView(point, 9, { animate: true });
          showError(t("locationOutside", "Your location is outside the supported Patna and Muzaffarpur gauge areas. Choose a focus district to see its gauge estimate."));
        }
      },
      () => showError(t("locationDenied", "Location permission was not granted. You can still choose Patna or Muzaffarpur.")),
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
    const mapPanel = $("mapPanel");
    const compactMap = window.matchMedia("(max-width: 900px)");
    const setMapDisclosure = (compact) => {
      mapPanel.open = !compact;
      $("mapDisclosureLabel").textContent = mapPanel.open ? t("hideMap", "Hide map") : t("showMap", "Show map");
    };
    mapPanel.addEventListener("toggle", () => {
      $("mapDisclosureLabel").textContent = mapPanel.open ? t("hideMap", "Hide map") : t("showMap", "Show map");
      if (mapPanel.open) window.requestAnimationFrame(() => map?.invalidateSize());
    });
    setMapDisclosure(compactMap.matches);
    compactMap.addEventListener("change", (event) => setMapDisclosure(event.matches));

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
      loadDischargeContext($("districtSelect").value);
      loadForecastOutlook($("districtSelect").value);
    });
    $("locateButton").addEventListener("click", useMyLocation);
    $("mapRefreshButton").addEventListener("click", () => selectDistrict());
    selectDistrict(false);
    loadDashboard();
    refreshTimer = window.setInterval(loadDashboard, REFRESH_MS);
    window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer), { once: true });
  });
})();
