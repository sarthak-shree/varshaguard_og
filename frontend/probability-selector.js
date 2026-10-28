(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const districtSelect = $("districtSelect");
  const card = $("probabilitySelectorCard");
  if (!card) return;

  const style = document.createElement("style");
  style.textContent = `
    #probabilitySelectorCard { background:linear-gradient(135deg,#18794e,#126b5b);color:#fff;border:0;box-shadow:0 12px 32px rgba(14,94,68,.18); }
    #probabilitySelectorCard .small-title { color:rgba(255,255,255,.78);letter-spacing:.12em;font-weight:800; }
    #probabilitySelectorCard h2 { margin:.2rem 0 .45rem;font-size:clamp(1.35rem,2vw,1.8rem); }
    #probabilitySelectorCard p { color:rgba(255,255,255,.82);line-height:1.5; }
    .probability-options { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem;margin:1.1rem 0; }
    .probability-option { display:flex;flex-direction:column;align-items:flex-start;gap:.35rem;text-align:left;padding:1rem;border:1px solid rgba(255,255,255,.3);border-radius:12px;background:rgba(255,255,255,.1);color:#fff;cursor:pointer;min-width:0; }
    .probability-option>span { font-size:1.35rem; }
    .probability-option strong { font-size:1rem; }
    .probability-option small { color:rgba(255,255,255,.78);line-height:1.4; }
    .probability-option.is-selected { background:#fff;color:#176b4b;border-color:#fff;box-shadow:0 0 0 2px rgba(255,255,255,.2); }
    .probability-option.is-selected small { color:#426b5b; }
    .probability-result { display:flex;flex-direction:column;align-items:center;gap:.55rem;padding:1.3rem .8rem;border:1px solid rgba(255,255,255,.22);border-radius:12px;background:rgba(0,0,0,.12);text-align:center; }
    #probabilityResultLabel { font-size:.88rem;color:rgba(255,255,255,.85); }
    #probabilityValue { font-size:clamp(2.5rem,7vw,4rem);line-height:1.1;letter-spacing:-.04em;font-variant-numeric:tabular-nums; }
    #probabilityStatus { font-size:.9rem;line-height:1.5; }
    .probability-meter { width:min(100%,480px);height:9px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.2); }
    .probability-meter[hidden] { display:none; }
    .probability-meter span { display:block;width:0;height:100%;background:#fff;border-radius:inherit;transition:width .25s ease; }
    #probabilitySelectorCard .probability-disclaimer { margin:.8rem 0 0;font-size:.78rem; }
    body.bihar-live-page #selectedRiskCard,body.bihar-live-page .bihar-overview .right-column,body.bihar-live-page .stage-trend-panel,body.bihar-live-page .two-column { display:none!important; }
    @media(max-width:520px) { .probability-options { gap:.55rem; } .probability-option { padding:.8rem; } .probability-option small { font-size:.72rem; } }
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
        ? "A validated heavy-rainfall probability model is not available yet."
        : "A reliable 24-hour estimate is currently unavailable."));
    }
  }

  async function refresh() {
    const sequence = ++requestSequence;
    const district = districtSelect && districtSelect.value ? districtSelect.value : "patna";
    const type = selectedType;
    $("probabilityResultLabel").textContent = (type === "flood" ? "Flood probability" : "Heavy rainfall probability") + " · next 24 hours";
    $("probabilityValue").textContent = "—%";
    $("probabilityMeter").hidden = true;
    setStatus("Loading backend forecast…");
    try {
      const response = await fetch("/api/bihar-live/probability?district=" + encodeURIComponent(district) + "&type=" + encodeURIComponent(type), {
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
      $("probabilityDisclaimer").textContent = type === "flood"
        ? "Estimates the chance that this CWC gauge reaches its published warning level within 24 hours. Not neighborhood inundation probability or an official alert."
        : "No percentage is shown until a heavy-rainfall prediction model is implemented and validated. No estimate is fabricated.";
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
