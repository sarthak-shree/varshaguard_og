async function boot() {
  const badge = document.getElementById("data-badge");
  const status = document.getElementById("status");
  const sources = document.getElementById("sources");
  try {
    const healthResponse = await fetch("/api/bihar-live/health", {cache: "no-store"});
    const health = await healthResponse.json();
    if (!healthResponse.ok) throw new Error("health request failed");
    badge.textContent = health.badge;
    status.textContent = "Mode: " + health.mode + " · Horizon: " + health.horizon_hours + "h · Districts: " + health.districts.join(", ");
    const sourceResponse = await fetch("/api/bihar-live/sources", {cache: "no-store"});
    const feed = await sourceResponse.json();
    sources.innerHTML = feed.sources.map(s => "<div>" + s.name + ": <b>" + s.status + "</b></div>").join("");
    const map = L.map("map").setView([25.9, 85.25], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);
    [[25.5941,85.1376,"Patna"],[26.1209,85.3647,"Muzaffarpur"]].forEach(([lat, lon, name]) =>
      L.marker([lat, lon]).addTo(map).bindPopup(name)
    );
  } catch (err) {
    badge.textContent = "System unavailable";
    status.textContent = err.message;
  }
}
boot();
