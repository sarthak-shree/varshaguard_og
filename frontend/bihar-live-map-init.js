(() => {
  function bootMap() {
    if (typeof initMap === "function") initMap();
    if (typeof updateMap === "function" && Array.isArray(records)) updateMap(records);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootMap, { once: true });
  else bootMap();
})();
