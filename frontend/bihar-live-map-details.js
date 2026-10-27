(() => {
  "use strict";
  const t = (key, fallback, values = {}) => String(fallback ?? key).replace(/\{(\w+)\}/g, (_, name) => values[name] == null ? "" : String(values[name]));

  window.showMapGaugeDetails = (prediction) => {
    if (!prediction) return;
    const state = prediction.risk_level || "unavailable";
    const districtKey = "district" + String(prediction.district || "").replace(/\s/g, "");
    const district = t(districtKey, prediction.district || "");
    const station = prediction.station_name ? " · " + prediction.station_name : "";
    const level = Number(prediction.current_stage_m);
    const observed = prediction.observed_at_ist;
    const date = observed ? new Date(observed.includes("+") || observed.endsWith("Z") ? observed : observed + "+05:30") : null;
    const time = date && !Number.isNaN(date.valueOf())
      ? date.toLocaleString("en-IN", {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata"
        }) + " IST"
      : "—";
    const percent = Number.isFinite(Number(prediction.risk_percentage))
      ? Number(prediction.risk_percentage)
      : Number(prediction.model_probability) * 100;
    const value = (key) => document.getElementById(key);

    value("mapGaugeName").textContent = district + station;
    if (prediction.status === "predicted" && Number.isFinite(percent)) {
      const riskName = t("risk" + state.charAt(0).toUpperCase() + state.slice(1), state);
      value("mapGaugeSignal").textContent = t("mapSelectedRisk", "{risk} model risk", { risk: riskName }) + " · " + percent.toFixed(1) + "%";
    } else if (prediction.status === "warning_level_reached" || prediction.status === "danger_level_reached") {
      value("mapGaugeSignal").textContent = t("thresholdReached", "A threshold has already been reached in the latest observation.");
    } else {
      value("mapGaugeSignal").textContent = prediction.message || t("noEstimate", "No current model estimate");
    }
    value("mapGaugeStage").textContent = Number.isFinite(level)
      ? t("latestLevel", "Latest level: {level} m", { level: level.toFixed(2) })
      : t("latestLevelUnavailable", "Latest level unavailable");
    value("mapGaugeUpdated").textContent = observed
      ? t("mapReadingAt", "Latest reading: {time}", { time })
      : t("freshnessWaiting", "Latest CWC reading: waiting for data");
    value("mapGaugeDetails").hidden = false;
  };

  document.getElementById("mapGaugeDetailsClose")?.addEventListener("click", () => {
    document.getElementById("mapGaugeDetails").hidden = true;
  });
})();
