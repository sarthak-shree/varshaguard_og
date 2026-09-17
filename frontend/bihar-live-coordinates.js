(() => {
  const key = value => String(value || "").toLowerCase().replace(/\s*\(cwc\)\s*/g, "").trim();
  async function attachStationCoordinates() {
    try {
      const response = await fetch("station_coordinates.json", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      const stations = payload.stations || {};
      if (Array.isArray(records)) {
        records.forEach(record => {
          const point = stations[key(record.station)];
          if (Array.isArray(point) && point.length === 2) {
            record.latitude = Number(point[0]);
            record.longitude = Number(point[1]);
          }
        });
        if (typeof updateMap === "function") updateMap(records);
      }
    } catch (error) {
      const status = document.getElementById("mapStatus");
      if (status) status.textContent = "Station coordinates unavailable";
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attachStationCoordinates, { once: true });
  else attachStationCoordinates();
})();
