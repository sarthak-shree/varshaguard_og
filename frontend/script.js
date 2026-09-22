
let latestAssistantContext = {};

function appendAssistantMessage(textValue, role = "bot") {
    const container = document.getElementById("assistantMessages");
    if (!container) return;
    const item = document.createElement("div");
    item.className = "assistant-message " + (role === "user" ? "assistant-user" : role === "error" ? "assistant-error" : "assistant-bot");
    item.textContent = textValue;
    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

function buildAssistantContext() {
    return {
        region: document.getElementById("currentRegion")?.textContent || "—",
        station: document.getElementById("selectedStationName")?.textContent || "—",
        risk_level: document.getElementById("riskLevel")?.textContent || "—",
        flood_probability: document.getElementById("probabilityValue")?.textContent || "—",
        forecast_window_hours: document.getElementById("horizon")?.textContent || "—",
        warning: document.getElementById("warning")?.textContent || "—",
        rain_rate_1h: document.getElementById("rainRateMetric")?.textContent || "—",
        rainfall_24h: document.getElementById("rain24Metric")?.textContent || "—",
        river_level: document.getElementById("riverLevelMetric")?.textContent || "—",
        river_threshold: document.getElementById("riverThresholdText")?.textContent || "—",
        prediction_timestamp: document.getElementById("stationFocusTime")?.textContent || "—",
        model_features: latestAssistantContext.features || {},
        data_note: "Prototype uses historical data; it is not a live monitoring feed."
    };
}

function setupAssistant() {
    const modal = document.getElementById("assistantModal");
    const openButtons = [
        document.getElementById("assistantOpenButton"),
        document.getElementById("assistantTopButton"),
    ].filter(Boolean);
    const closeButton = document.getElementById("assistantCloseButton");
    const form = document.getElementById("assistantForm");
    const input = document.getElementById("assistantInput");
    const sendButton = document.getElementById("assistantSendButton");

    if (!modal || !openButtons.length || !closeButton || !form || !input || !sendButton) return;

    const open = () => {
        latestAssistantContext = buildAssistantContext();
        modal.classList.remove("hidden");
        input.focus();
    };
    const close = () => modal.classList.add("hidden");

    openButtons.forEach((button) => button.addEventListener("click", open));
    closeButton.addEventListener("click", close);
    modal.addEventListener("click", (event) => {
        if (event.target === modal) close();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") close();
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = input.value.trim();
        if (!question) return;

        appendAssistantMessage(question, "user");
        input.value = "";
        input.disabled = true;
        sendButton.disabled = true;
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
        } catch (error) {
            appendAssistantMessage(error.message, "error");
        } finally {
            input.disabled = false;
            sendButton.disabled = false;
            sendButton.textContent = "Send";
            input.focus();
        }
    });
}

const API_BASE = "";

let map;
let markerLayer;
let rainfallChart;
let stationMarkers = new Map();

const regionCenters = {
    Assam: [26.1445, 91.7362],
    Uttarakhand: [30.3165, 78.0322],
};

const RISK_CONFIG = {
    LOW: { className: "risk-low", trend: "→ Stable", label: "Normal" },
    MEDIUM: { className: "risk-medium", trend: "↑ Watch", label: "Watch" },
    HIGH: { className: "risk-high", trend: "↑ Warning", label: "Warning" },
};

function showMessage(text) {
    const message = document.getElementById("message");
    if (!message) return;
    message.textContent = text;
    message.classList.remove("hidden");
}

function hideMessage() {
    const message = document.getElementById("message");
    if (message) message.classList.add("hidden");
}

async function getJson(url) {
    const response = await fetch(url);
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
        throw new Error(`Expected JSON from ${url}, but received HTML/text (${response.status}).`);
    }

    const data = await response.json();
    if (!response.ok || data.success === false) {
        throw new Error(data.error || "API request failed");
    }
    return data;
}

function setupMap() {
    map = L.map("map").setView(regionCenters.Assam, 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
}

function riskClassName(risk) {
    return RISK_CONFIG[risk]?.className || "risk-low";
}

function riskLabel(risk) {
    return RISK_CONFIG[risk]?.label || "Normal";
}

function riskTrend(risk) {
    return RISK_CONFIG[risk]?.trend || "→ Stable";
}

function formatNumber(value, digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "—";
}

function formatTimestamp(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

function getLatestRow(rows = []) {
    return rows.length ? rows[rows.length - 1] : null;
}

function updateRiskCard(data, latestRow = null) {
    const card = document.getElementById("riskCard");
    const risk = String(data.risk || "LOW").toUpperCase();
    card.className = "risk-card " + riskClassName(risk);

    document.getElementById("riskLevel").textContent = risk;
    document.getElementById("riskTrend").textContent = riskTrend(risk);

    const probability = Number(data.flood_probability) || 0;
    const percentage = Math.max(0, Math.min(100, Math.round(probability * 100)));

    document.getElementById("probabilityValue").textContent = `${percentage}%`;
    document.getElementById("riskCardBarFill").style.width = `${percentage}%`;
    document.getElementById("warning").textContent = data.warning || "Continue monitoring current conditions.";
    document.getElementById("horizon").textContent = data.prediction_horizon_hours || 24;

    const stationName = data.station || "Selected station";
    document.getElementById("selectedStationName").textContent = stationName;
    document.getElementById("stationFocusName").textContent = stationName;
    document.getElementById("stationFocusRisk").textContent = `${risk} · ${percentage}%`;

    const timestamp = data.data_timestamp || latestRow?.timestamp || "";
    document.getElementById("stationFocusTime").textContent = formatTimestamp(timestamp);
}

function humanizeFeature(name) {
    const labels = {
        rainfall_1h: "Recent rainfall",
        rainfall_3h: "3-hour rainfall",
        rainfall_6h: "6-hour rainfall",
        rainfall_12h: "12-hour rainfall",
        rainfall_24h: "24-hour rainfall",
        rainfall_72h: "72-hour rainfall",
        is_monsoon: "Seasonal signal",
        river_level: "River level",
        river_level_change: "River level change",
    };
    return labels[name] || name.replaceAll("_", " ");
}

function featureImportanceValue(name, value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0;
    if (name === "is_monsoon") return Math.min(100, Math.abs(numeric) * 100);
    return Math.min(100, Math.abs(numeric));
}

function updateFeatures(features) {
    latestAssistantContext.features = features || {};
    const featureList = document.getElementById("featureList");
    const drivers = document.getElementById("riskDrivers");
    featureList.innerHTML = "";
    drivers.innerHTML = "";

    const entries = Object.entries(features || {});
    entries.forEach(([name, value]) => {
        const item = document.createElement("div");
        item.className = "feature";
        item.innerHTML = `<span>${humanizeFeature(name)}</span><strong>${value}</strong>`;
        featureList.appendChild(item);
    });

    const driverEntries = entries.slice(0, 4);
    driverEntries.forEach(([name, value]) => {
        const item = document.createElement("div");
        item.className = "risk-driver";
        const barValue = featureImportanceValue(name, value);
        item.innerHTML = `
            <div class="risk-driver-head">
                <span class="risk-driver-name">${humanizeFeature(name)}</span>
                <span class="risk-driver-value">${value}</span>
            </div>
            <div class="risk-driver-bar"><div class="risk-driver-fill" style="width:${barValue}%"></div></div>
        `;
        drivers.appendChild(item);
    });

    if (!entries.length) {
        drivers.innerHTML = '<div class="plain-text">Model feature details are unavailable for this prediction.</div>';
    }
}

function markerColor(risk) {
    if (risk === "HIGH") return "#F87171";
    if (risk === "MEDIUM") return "#FBBF24";
    return "#34D399";
}

function createRiskMarker(station) {
    const percentage = Math.round(Number(station.flood_probability || 0) * 100);
    const risk = String(station.risk || "LOW").toUpperCase();
    const isSelected = station.station === document.getElementById("stationSelect")?.value;

    const riverLevel = station.river_level ?? station.level;
    const riverText = Number.isFinite(Number(riverLevel)) ? `${formatNumber(riverLevel, 2)} m` : "—";

    const marker = L.circleMarker([station.latitude, station.longitude], {
        radius: isSelected ? 11 : 8,
        color: "white",
        weight: isSelected ? 3 : 2,
        fillColor: markerColor(risk),
        fillOpacity: 0.92,
    }).bindPopup(`
        <div style="min-width:190px">
          <strong>${station.station}</strong><br>
          <span>Risk:</span> <strong>${riskLabel(risk)}</strong><br>
          <span>Flood probability:</span> <strong>${percentage}%</strong><br>
          <span>River level:</span> <strong>${riverText}</strong><br>
          <span>Updated:</span> ${formatTimestamp(station.data_timestamp)}
        </div>
    `).addTo(markerLayer);

    marker.on("click", () => {
        const stationSelect = document.getElementById("stationSelect");
        if (stationSelect && stationSelect.value !== station.station) {
            stationSelect.value = station.station;
            loadStation(station.station);
        }
    });

    return marker;
}

function updateMap(data, riskMap) {
    markerLayer.clearLayers();
    stationMarkers.clear();

    const stations = riskMap?.stations || [];
    const selectedCenter = [Number(data.latitude), Number(data.longitude)];
    if (selectedCenter.every(Number.isFinite)) map.setView(selectedCenter, 9);

    stations.forEach((station) => {
        if (!Number.isFinite(Number(station.latitude)) || !Number.isFinite(Number(station.longitude))) return;
        const marker = createRiskMarker(station);
        stationMarkers.set(station.station, marker);
    });

    if (!stations.length && Number.isFinite(Number(data.latitude)) && Number.isFinite(Number(data.longitude))) {
        const fallbackStation = {
            station: data.station,
            latitude: data.latitude,
            longitude: data.longitude,
            flood_probability: data.flood_probability,
            risk: data.risk,
            data_timestamp: data.data_timestamp,
            river_level: data.river_level ?? data.level,
        };
        stationMarkers.set(data.station, createRiskMarker(fallbackStation));
    }
}

function setupChart() {
    const canvas = document.getElementById("rainfallChart");
    rainfallChart = new Chart(canvas, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "1h rainfall (mm)",
                    data: [],
                    borderColor: "#197f89",
                    backgroundColor: "rgba(25,127,137,.10)",
                    borderWidth: 2,
                    tension: 0.32,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                },
                {
                    label: "24h rainfall (mm)",
                    data: [],
                    borderColor: "#f59e0b",
                    backgroundColor: "rgba(245,158,11,.06)",
                    borderWidth: 2,
                    tension: 0.32,
                    fill: false,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { labels: { color: "#667280", boxWidth: 14 } } },
            scales: {
                x: {
                    ticks: { color: "#667280", maxTicksLimit: 8 },
                    grid: { color: "rgba(23,33,43,0.06)" },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#667280" },
                    grid: { color: "rgba(23,33,43,0.06)" },
                    title: { display: true, text: "Rainfall (mm)", color: "#667280" },
                },
            },
        },
    });
}

function updateChart(rows) {
    const stationName = document.getElementById("selectedStationName")?.textContent || "Selected station";
    const chartSubtitle = document.getElementById("chartSubtitle");
    if (chartSubtitle) chartSubtitle.textContent = stationName;

    rainfallChart.data.labels = rows.map((row) => String(row.timestamp || "").slice(11, 16) || String(row.timestamp || "").slice(5, 16));
    rainfallChart.data.datasets[0].data = rows.map((row) => Number(row.rainfall_1h) || 0);
    rainfallChart.data.datasets[1].data = rows.map((row) => Number(row.rainfall_24h) || 0);
    rainfallChart.update();
}

function updateMetrics(risk, rows) {
    const latest = getLatestRow(rows);
    const rain1 = latest?.rainfall_1h;
    const rain24 = latest?.rainfall_24h;
    const river = latest?.river_level ?? latest?.level ?? risk?.river_level ?? risk?.level;

    document.getElementById("rainRateMetric").textContent = Number.isFinite(Number(rain1)) ? `${formatNumber(rain1, 1)} mm` : "—";
    document.getElementById("rain24Metric").textContent = Number.isFinite(Number(rain24)) ? `${formatNumber(rain24, 1)} mm` : "—";
    document.getElementById("riverLevelMetric").textContent = Number.isFinite(Number(river)) ? `${formatNumber(river, 2)} m` : "—";
    document.getElementById("stationFocusRain1").textContent = Number.isFinite(Number(rain1)) ? `${formatNumber(rain1, 1)} mm` : "—";
    document.getElementById("stationFocusRain24").textContent = Number.isFinite(Number(rain24)) ? `${formatNumber(rain24, 1)} mm` : "—";
    document.getElementById("stationFocusRiver").textContent = Number.isFinite(Number(river)) ? `${formatNumber(river, 2)} m` : "—";

    const threshold = risk?.danger_level ?? risk?.dangerLevel ?? latest?.danger_level;
    document.getElementById("riverThresholdText").textContent = Number.isFinite(Number(threshold))
        ? `Danger level ${formatNumber(threshold, 2)} m`
        : "Threshold unavailable";

}

function updateHealthUi(data) {
    const api = data?.status === "ok" ? "ONLINE" : "OFFLINE";
    const model = data?.model || "UNKNOWN";
    const weather = data?.data || "UNKNOWN";
    const prediction = data?.prediction || "UNKNOWN";

    document.getElementById("apiStatus").textContent = api;
    document.getElementById("predictionStatus").textContent = prediction;
    document.getElementById("dataStatus").textContent = weather;

    const telemetry = document.getElementById("telemetryStatus");
    if (telemetry) telemetry.textContent = weather;

    const overall = document.getElementById("overallHealth");
    const good = [api, String(model).toUpperCase(), String(weather).toUpperCase(), String(prediction).toUpperCase()]
        .every((value) => !["OFFLINE", "ERROR", "FAILED"].some((bad) => value.includes(bad)));

    overall.textContent = good ? "HEALTHY" : "DEGRADED";
    overall.style.color = good ? "#2e8b68" : "#b94a45";
    overall.style.background = good ? "#edf7f3" : "#fbefee";
}

async function updateHealth() {
    try {
        const data = await getJson(`${API_BASE}/api/health`);
        updateHealthUi(data);
    } catch (error) {
        updateHealthUi({ status: "error", model: "ERROR", data: "ERROR", prediction: "ERROR" });
    }
}

async function loadStations(region) {
    const stationSelect = document.getElementById("stationSelect");
    if (!stationSelect) return [];

    stationSelect.innerHTML = '<option value="">Loading stations...</option>';
    stationSelect.disabled = true;

    const data = await getJson(`${API_BASE}/api/stations?region=${encodeURIComponent(region)}`);
    const stations = data.stations || [];

    stationSelect.innerHTML = "";
    if (!stations.length) {
        stationSelect.innerHTML = '<option value="">No stations available</option>';
        return stations;
    }

    stations.forEach((station) => {
        const option = document.createElement("option");
        option.value = station.station;
        option.textContent = station.station;
        stationSelect.appendChild(option);
    });

    stationSelect.disabled = false;
    return stations;
}

async function loadRiskMap(region, knownStations = null) {
    try {
        return await getJson(`${API_BASE}/api/flood-risk-map?region=${encodeURIComponent(region)}`);
    } catch (error) {
        const stations = knownStations || (await loadStations(region));
        const results = await Promise.all(
            stations.map(async (station) => {
                const query = `region=${encodeURIComponent(region)}&station=${encodeURIComponent(station.station)}`;
                const risk = await getJson(`${API_BASE}/api/flood-risk?${query}`);
                return {
                    region,
                    station: risk.station || station.station,
                    latitude: Number(risk.latitude ?? station.latitude),
                    longitude: Number(risk.longitude ?? station.longitude),
                    flood_probability: Number(risk.flood_probability || 0),
                    risk: risk.risk,
                    data_timestamp: risk.data_timestamp || "—",
                    river_level: risk.river_level ?? station.river_level ?? station.level,
                    danger_level: risk.danger_level ?? station.danger_level,
                };
            })
        );

        return { success: true, region, stations: results, count: results.length };
    }
}

async function loadStation(station) {
    const region = document.getElementById("regionSelect").value;
    if (!station) return;

    hideMessage();

    try {
        const query = `region=${encodeURIComponent(region)}&station=${encodeURIComponent(station)}`;
        const [risk, rainfall, stations] = await Promise.all([
            getJson(`${API_BASE}/api/flood-risk?${query}`),
            getJson(`${API_BASE}/api/rainfall?${query}`),
            getJson(`${API_BASE}/api/stations?region=${encodeURIComponent(region)}`),
        ]);

        const rows = rainfall.rainfall || [];
        const latest = getLatestRow(rows);
        const riskMap = await loadRiskMap(region, stations.stations);

        document.getElementById("currentRegion").textContent = region;
        updateRiskCard(risk, latest);
        updateFeatures(risk.features);
        updateChart(rows);
        updateMetrics(risk, rows);
        updateMap(risk, riskMap);
        await updateHealth();
    } catch (error) {
        showMessage(error.message);
        await updateHealth();
    }
}

async function loadRegion(region) {
    hideMessage();
    document.getElementById("currentRegion").textContent = region;

    try {
        const stations = await loadStations(region);
        if (!stations.length) throw new Error(`No stations available for ${region}`);

        const stationSelect = document.getElementById("stationSelect");
        const firstStation = stations[0].station;
        stationSelect.value = firstStation;
        await loadStation(firstStation);
    } catch (error) {
        showMessage(error.message);
        await updateHealth();
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    setupMap();
    setupChart();
    setupAssistant();

    const regionSelect = document.getElementById("regionSelect");
    const stationSelect = document.getElementById("stationSelect");

    regionSelect.addEventListener("change", () => loadRegion(regionSelect.value));
    stationSelect.addEventListener("change", () => loadStation(stationSelect.value));

    await updateHealth();
    await loadRegion(regionSelect.value);
});