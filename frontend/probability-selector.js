(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const districtSelect = $("districtSelect");
  const card = $("probabilitySelectorCard");
  if (!card) return;
  let isSignedIn = false;
  let authReady = false;
  let authRequest = 0;
  let selectedType = "flood";
  let requestSequence = 0;

  const style = document.createElement("style");
  style.textContent = `
    .probability-top-controls { display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin:0;min-width:0; }
    .probability-top-controls .selector-panel { display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:10px;max-width:100%;min-width:0; }
    .probability-top-controls .selector-panel .field { flex:1;min-width:0; }
    .probability-top-controls .selector-panel .bihar-locate { width:100%;min-width:0; }
    #probabilitySelectorCard { width:100%;min-width:0;box-sizing:border-box;padding:20px;background:linear-gradient(145deg,#146b50 0%,#0e594f 100%);color:#fff;border:1px solid rgba(255,255,255,.12);box-shadow:0 16px 38px rgba(14,94,68,.18);border-radius:18px; }
    #probabilitySelectorCard .small-title { color:rgba(255,255,255,.78);letter-spacing:.14em;font-weight:800;font-size:10px;margin:0; }
    #probabilitySelectorCard h2 { margin:.3rem 0 .45rem;font-size:clamp(1.2rem,1.8vw,1.55rem);line-height:1.18; }
    #probabilitySelectorCard .probability-heading>p:last-child { margin:.4rem 0 .8rem;font-size:.82rem;line-height:1.5;color:rgba(255,255,255,.85); }
    .probability-options { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem;margin:.85rem 0; }
    .probability-option { display:flex;flex-direction:column;align-items:flex-start;gap:.28rem;text-align:left;padding:.8rem .85rem;border:1px solid rgba(255,255,255,.3);border-radius:12px;background:rgba(255,255,255,.09);color:#fff;cursor:pointer;min-width:0;transition:background .18s ease,border-color .18s ease,transform .18s ease; }
    .probability-option:hover { transform:translateY(-1px);background:rgba(255,255,255,.15); }
    .probability-option>span { font-size:1.15rem;line-height:1; }
    .probability-option strong { font-size:.9rem;line-height:1.2; }
    .probability-option small { color:rgba(255,255,255,.78);font-size:.7rem;line-height:1.35; }
    .probability-option.is-selected { background:#fff;color:#145d48;border-color:#fff;box-shadow:0 5px 18px rgba(0,0,0,.12); }
    .probability-option.is-selected small { color:#4b6b5e; }
    .probability-result { position:relative;display:flex;flex-direction:column;align-items:center;gap:.45rem;padding:1rem .8rem;border:1px solid rgba(255,255,255,.22);border-radius:13px;background:rgba(0,0,0,.13);text-align:center;min-height:140px;justify-content:center; }
    .probability-result__content { display:flex;flex-direction:column;align-items:center;gap:.45rem;width:100%;min-width:0; }
    #probabilitySelectorCard.is-locked .probability-result__content { filter:blur(8px);user-select:none;pointer-events:none; }
    #probabilitySelectorCard .probability-lock-overlay { display:none;position:absolute;inset:0;z-index:2;align-items:center;justify-content:center;flex-direction:column;padding:15px;border-radius:13px;background:rgba(5,44,35,.72);text-align:center;backdrop-filter:blur(3px); }
    #probabilitySelectorCard.is-locked .probability-lock-overlay { display:flex; }
    .probability-lock-icon { display:grid;place-items:center;width:42px;height:42px;margin-bottom:8px;border-radius:50%;background:rgba(255,255,255,.13);font-size:20px; }
    .probability-lock-overlay strong { display:block;font-size:.95rem; }
    .probability-lock-overlay p { max-width:310px;margin:5px 0 12px;font-size:.75rem;line-height:1.4;color:rgba(255,255,255,.82); }
    .probability-login-button { min-height:42px;border:0;border-radius:999px;padding:10px 19px;background:#fff;color:#126b5b;font-weight:800;cursor:pointer;box-shadow:0 5px 16px rgba(0,0,0,.12); }
    .probability-login-button:focus-visible,.probability-option:focus-visible { outline:3px solid #f8d777;outline-offset:3px; }
    #probabilityResultLabel { font-size:.75rem;line-height:1.4;color:rgba(255,255,255,.85); }
    #probabilityValue { font-size:clamp(2.2rem,4vw,3rem);line-height:1.05;letter-spacing:-.04em;font-variant-numeric:tabular-nums; }
    #probabilityStatus { font-size:.75rem;line-height:1.45;overflow-wrap:anywhere;color:rgba(255,255,255,.88); }
    .probability-meter { width:min(100%,480px);height:8px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.2); }
    .probability-meter[hidden] { display:none; }
    .probability-meter span { display:block;width:0;height:100%;background:#fff;border-radius:inherit;transition:width .25s ease; }
    #probabilitySelectorCard .probability-disclaimer { margin:.7rem 0 0;font-size:.68rem;line-height:1.45;color:rgba(255,255,255,.76); }
    @media(min-width:900px) { .probability-top-controls { grid-template-columns:minmax(0,1fr);align-items:stretch; } }
    @media(max-width:520px) {
      .probability-options { gap:.45rem; }
      .probability-option { padding:.72rem .65rem; }
      .probability-option small { font-size:.65rem; }
      #probabilitySelectorCard { padding:15px; }
    }
  `;
  document.head.appendChild(style);

  const setStatus = (message) => { $("probabilityStatus").textContent = message; };
  const resultPanel = card.querySelector(".probability-result");
  const resultContent = document.createElement("div");
  resultContent.className = "probability-result__content";
  if (resultPanel) {
    const originalChildren = Array.from(resultPanel.childNodes);
    originalChildren.forEach((node) => resultContent.appendChild(node));
    resultPanel.appendChild(resultContent);
  }
  const lockOverlay = document.createElement("div");
  lockOverlay.className = "probability-lock-overlay";
  lockOverlay.innerHTML = '<span class="probability-lock-icon" aria-hidden="true">🔒</span><strong>Heavy-rainfall details are locked</strong><p>Sign in to load the rainfall forecast and see its full details.</p><button class="probability-login-button" type="button">Login / Sign Up</button>';
  resultPanel?.appendChild(lockOverlay);
  lockOverlay.querySelector("button").addEventListener("click", () => {
    window.location.href = "/login.html?next=" + encodeURIComponent(window.location.pathname + window.location.search + "#probabilitySelectorCard");
  });
  function applyAuthState() {
    const locked = !isSignedIn && selectedType === "heavy_rainfall";
    card.classList.toggle("is-locked", locked);
    card.setAttribute("aria-label", locked ? "Heavy-rainfall details locked. Sign in to load and view." : "Forecast details");
  }
  async function checkAuth() {
    const requestId = ++authRequest;
    try {
      const response = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
      if (requestId !== authRequest) return;
      isSignedIn = response.ok;
    } catch { isSignedIn = false; }
    authReady = true;
    applyAuthState();
    if (selectedType === "heavy_rainfall" && isSignedIn) refresh();
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) checkAuth(); });

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
    applyAuthState();
    if (!authReady) return;
    if (!isSignedIn && type === "heavy_rainfall") {
      $("probabilityResultLabel").textContent = "Heavy-rainfall forecast details";
      $("probabilityValue").textContent = "—%";
      $("probabilityMeter").hidden = true;
      $("probabilityMeterFill").style.width = "0%";
      setStatus("Sign in to load the protected rainfall forecast.");
      return;
    }
    $("probabilityResultLabel").textContent = type === "flood"
      ? "CWC gauge warning-level probability · next 24 hours"
      : "Peak hourly precipitation chance · next 24 hours";
    $("probabilityValue").textContent = "—%";
    $("probabilityMeter").hidden = true;
    setStatus("Loading backend forecast…");
    try {
      if (type === "heavy_rainfall") {
        const response = await fetch("/api/bihar-live/probability?district=" + encodeURIComponent(district) + "&type=heavy_rainfall", {
          credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" }
        });
        if (response.status === 401) {
          isSignedIn = false;
          applyAuthState();
          setStatus("Your session has expired. Sign in again to load the protected rainfall forecast.");
          return;
        }
        const data = await response.json();
        if (sequence !== requestSequence) return;
        if (!response.ok || !data || data.success === false) throw new Error(data && data.error || "The rainfall service is unavailable.");
        if (data.available && Number.isFinite(Number(data.probability_percent))) {
          const percent = Math.max(0, Math.min(100, Number(data.probability_percent)));
          $("probabilityValue").textContent = percent.toFixed(1) + "%";
          $("probabilityMeter").hidden = false;
          $("probabilityMeter").setAttribute("aria-valuenow", percent.toFixed(1));
          $("probabilityMeterFill").style.width = percent + "%";
          setStatus((data.location || district) + " · protected forecast details loaded. Research estimate only.");
        } else {
          renderUnavailable(data, type);
        }
        $("probabilityDisclaimer").textContent = data.message || "A validated heavy-rainfall probability model is not available yet. No heavy-rainfall probability is fabricated.";
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
      applyAuthState();
      card.querySelectorAll("[data-forecast-type]").forEach((option) => {
        const selected = option === button;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-pressed", String(selected));
      });
      if (selectedType !== "heavy_rainfall" || isSignedIn) refresh();
      else {
        $("probabilityResultLabel").textContent = "Heavy-rainfall forecast details";
        $("probabilityValue").textContent = "—%";
        $("probabilityMeter").hidden = true;
        setStatus("Sign in to load the protected rainfall forecast.");
      }
    });
  });
  if (districtSelect) districtSelect.addEventListener("change", refresh);
  card.addEventListener("click", (event) => { if (event.target.closest(".probability-login-button")) event.stopPropagation(); });
  checkAuth().then(() => { if (selectedType === "flood") refresh(); });
  window.setInterval(refresh, 5 * 60 * 1000);
})();
