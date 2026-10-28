(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const districtSelect = $("districtSelect");
  const card = $("probabilitySelectorCard");
  if (!card) return;

  const style = document.createElement("style");
  style.textContent = `
    .probability-top-controls { display:grid;grid-template-columns:minmax(0,1fr);gap:10px;margin:0;min-width:0; }
    .probability-top-controls .selector-panel { display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:10px;max-width:100%;min-width:0; }
    .probability-top-controls .selector-panel .field { flex:1;min-width:0; }
    .probability-top-controls .selector-panel .bihar-locate { width:100%;min-width:0; }
    #probabilitySelectorCard { width:100%;min-width:0;box-sizing:border-box;padding:16px 17px;background:linear-gradient(135deg,#18794e,#126b5b);color:#fff;border:0;box-shadow:0 12px 32px rgba(14,94,68,.18); }
    #probabilitySelectorCard .small-title { color:rgba(255,255,255,.78);letter-spacing:.12em;font-weight:800;font-size:9px;margin:0; }
    #probabilitySelectorCard h2 { margin:.25rem 0 .4rem;font-size:clamp(1.15rem,1.5vw,1.45rem);line-height:1.18; }
    #probabilitySelectorCard .probability-heading>p:last-child { margin:.4rem 0 .75rem;font-size:.78rem;line-height:1.45; }
    .probability-options { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem;margin:.7rem 0; }
    .probability-option { display:flex;flex-direction:column;align-items:flex-start;gap:.22rem;text-align:left;padding:.65rem .7rem;border:1px solid rgba(255,255,255,.3);border-radius:9px;background:rgba(255,255,255,.1);color:#fff;cursor:pointer;min-width:0; }
    .probability-option>span { font-size:1rem;line-height:1; }
    .probability-option strong { font-size:.82rem;line-height:1.2; }
    .probability-option small { color:rgba(255,255,255,.78);font-size:.66rem;line-height:1.3; }
    .probability-option.is-selected { background:#fff;color:#176b4b;border-color:#fff;box-shadow:0 0 0 1px rgba(255,255,255,.2); }
    .probability-option.is-selected small { color:#426b5b; }
    .probability-result { display:flex;flex-direction:column;align-items:center;gap:.35rem;padding:.75rem .65rem;border:1px solid rgba(255,255,255,.22);border-radius:9px;background:rgba(0,0,0,.12);text-align:center; }
    #probabilityResultLabel { font-size:.72rem;line-height:1.35;color:rgba(255,255,255,.85); }
    #probabilityValue { font-size:clamp(2rem,4vw,2.8rem);line-height:1.05;letter-spacing:-.04em;font-variant-numeric:tabular-nums; }
    #probabilityStatus { font-size:.72rem;line-height:1.4;overflow-wrap:anywhere; }
    .probability-meter { width:min(100%,480px);height:7px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.2); }
    .probability-meter[hidden] { display:none; }
    .probability-meter span { display:block;width:0;height:100%;background:#fff;border-radius:inherit;transition:width .25s ease; }
    #probabilitySelectorCard .probability-disclaimer { margin:.6rem 0 0;font-size:.66rem;line-height:1.4; }
    @media(min-width:900px) {
      .probability-top-controls { grid-template-columns:minmax(0,1fr);align-items:stretch; }
      .probability-top-controls .selector-panel { flex-direction:column;align-items:stretch;justify-content:flex-start; }
      .probability-options { max-width:none; }
    }
    @media(max-width:520px) {
      .probability-options { gap:.4rem; }
      .probability-option { padding:.6rem; }
      .probability-option small { font-size:.63rem; }
      #probabilitySelectorCard { padding:14px; }
    }
  `;
  document.head.appendChild(style);

  let selectedType = "flood";
  let requestSequence = 0;
  const setStatus = (message) => { $("probabilityStatus").textContent = message; };

  function renderUnavailable(data, type) {
    $("probabilityValue").textContent = "—%";
    $("probabilityMeter").hidden = true;
    $("probabilityMeterFill").style.width = "0%";
    if (data && data.observed_threshold_reached) {
      setStatus("Observed CWC warning/danger threshold reached. This is an observation, not a forecast probability.");
    } else {
      setStatus((data && data.message) || (type === "heavy_rainfall"
        ? "The weather forecast is currently unavailable."
        : "A reliable 24-hour estimate is currently unavailable."));
    }
  }

  function renderWeatherContext(data, district) {
    const percent = data && data.available ? data.peak_hourly_rainfall_probability_pct : null;
    if (percent !== null && percent !== undefined && Number.isFinite(Number(percent))) {
      const bounded = Math.max(0, Math.min(100, Number(percent)));
      $("probabilityValue").textContent = bounded.toFixed(0) + "%";
      $("probabilityMeter").hidden = false;
      $("probabilityMeter").setAttribute("aria-valuenow", bounded.toFixed(0));
      $("probabilityMeterFill").style.width = bounded + "%";
    } else {
      $("probabilityValue").textContent = "—%";
      $("probabilityMeter").hidden = true;
      $("probabilityMeterFill").style.width = "0%";
    }
    if (!data || !data.available) {
      setStatus((data && data.message) || "The rainfall outlook is currently unavailable.");
      return;
    }
    const rain = data.forecast_rainfall_24h_mm;
    const wetHours = data.wet_hours_forecast;
    const parts = [];
    if (rain !== null && rain !== undefined) parts.push("forecast total " + Number(rain).toFixed(1) + " mm/24h");
    if (wetHours !== null && wetHours !== undefined) parts.push(String(wetHours) + " wet hours");
    setStatus((data.location || district) + " · " + parts.join(" · ") +
      ". Weather-model context only; this is not a validated heavy-rainfall risk score.");
  }

  async function refresh() {
    const sequence = ++requestSequence;
    const district = districtSelect && districtSelect.value ? districtSelect.value : "patna";
    const type = selectedType;
    $("probabilityResultLabel").textContent = type === "flood"
      ? "CWC gauge warning-level probability · next 24 hours"
      : "Peak hourly precipitation chance · next 24 hours";
    $("probabilityValue").textContent = "—%";
    $("probabilityMeter").hidden = true;
    setStatus("Loading backend forecast…");
    try {
      if (type === "heavy_rainfall") {
        const response = await fetch("/api/bihar-live/weather?district=" + encodeURIComponent(district), {
          cache: "no-store", headers: { Accept: "application/json" }
        });
        const data = await response.json();
        if (sequence !== requestSequence) return;
        if (!response.ok || !data || data.success === false) throw new Error(data && data.error || "The weather service is unavailable.");
        renderWeatherContext(data, district);
        $("probabilityDisclaimer").textContent = "This percentage is the weather provider's chance of precipitation during the peak forecast hour—not the probability of heavy rainfall, flooding, or an official alert. The 24-hour rainfall total is shown below.";
        return;
      }

      const response = await fetch("/api/bihar-live/probability?district=" + encodeURIComponent(district) + "&type=flood", {
        cache: "no-store", headers: { Accept: "application/json" }
      });
      const data = await response.json();
      if (sequence !== requestSequence) return;
      if (!response.ok || !data || data.success === false) throw new Error(data && data.error || "The forecast service is unavailable.");
      if (data.available && Number.isFinite(Number(data.probability_percent))) {
        const percent = Math.max(0, Math.min(100, Number(data.probability_percent)));
        $("probabilityValue").textContent = percent.toFixed(1) + "%";
        $("probabilityMeter").hidden = false;
        $("probabilityMeter").setAttribute("aria-valuenow", percent.toFixed(1));
        $("probabilityMeterFill").style.width = percent + "%";
        setStatus((data.location || districtSelect.options[districtSelect.selectedIndex].text) + " · forecast through " +
          (data.forecast_end_ist || "the next 24 hours") + ". Research estimate only.");
      } else {
        renderUnavailable(data, type);
      }
      $("probabilityDisclaimer").textContent = "Estimates the chance that this CWC gauge reaches its published warning level within 24 hours. Not neighborhood inundation probability or an official alert.";
    } catch (error) {
      if (sequence !== requestSequence) return;
      renderUnavailable({ message: error && error.message }, type);
    }
  }

  card.querySelectorAll("[data-forecast-type]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedType = button.dataset.forecastType;
      card.querySelectorAll("[data-forecast-type]").forEach((option) => {
        const selected = option === button;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-pressed", String(selected));
      });
      refresh();
    });
  });
  if (districtSelect) districtSelect.addEventListener("change", refresh);
  document.addEventListener("DOMContentLoaded", refresh);
  refresh();
  window.setInterval(refresh, 5 * 60 * 1000);
})();
