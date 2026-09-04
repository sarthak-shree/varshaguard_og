const API_BASE = "";

let map;
let markerLayer;
let rainfallChart;
let stationMarkers = new Map();

const regionCenters = {
    Assam: [26.1445, 91.7362],
    Uttarakhand: [30.3165, 78.0322],
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
    if (risk === "HIGH") return "risk-high";
    if (risk === "MEDIUM") return "risk-medium";
    return "risk-low";
}

function updateRiskCard(data) {
    const card = document.getElementById("riskCard");
    card.className = "risk-card " + riskClassName(data.risk);

    document.getElementById("riskLevel").textContent = data.risk;
    document.getElementById("probability").textContent = Math.round(data.flood_probability * 100) + "%";
    document.getElementById("warning").textContent = data.warning;
    document.getElementById("horizon").textContent = data.prediction_horizon_hours;

    const stationName = document.getElementById("selectedStationName");
    if (stationName) stationName.textContent = data.station || "Selected station";

    const dataTime = document.getElementById("dataTimestamp");
    if (dataTime) dataTime.textContent = data.data_timestamp || "—";
}

function updateFeatures(features) {
    const featureList = document.getElementById("featureList");
    featureList.innerHTML = "";

    Object.keys(features || {}).forEach((name) => {
        const item = document.createElement("div");
        item.className = "feature";
        item.innerHTML = `<span>${name}</span><strong>${features[name]}</strong>`;
        featureList.appendChild(item);
    });
}

function markerColor(risk) {
    if (risk === "HIGH") return "#F87171";
    if (risk === "MEDIUM") return "#FBBF24";
    return "#34D399";
}

function updateMap(data, stations) {
    markerLayer.clearLayers();
    stationMarkers.clear();

    const selectedCenter = [data.latitude, data.longitude];
    map.setView(selectedCenter, 9);

    stations.forEach((station) => {
        const isSelected = station.station === data.station;
        const marker = L.circleMarker([station.latitude, station.longitude], {
            radius: isSelected ? 10 : 7,
            color: isSelected ? "white" : "#2FB8C6",
            weight: isSelected ? 3 : 2,
            fillColor: isSelected ? markerColor(data.risk) : "#2FB8C6",
            fillOpacity: isSelected ? 0.95 : 0.65,
        })
            .bindPopup(`<strong>${station.station}</strong><br>${isSelected ? `${data.risk} risk · ${Math.round(data.flood_probability * 100)}%` : "Click to select this station"}`)
            .addTo(markerLayer);

        marker.on("click", () => {
            const stationSelect = document.getElementById("stationSelect");
            if (stationSelect) {
                stationSelect.value = station.station;
                loadStation(station.station);
            }
        });

        stationMarkers.set(station.station, marker);
    });
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
                    borderColor: "#2FB8C6",
                    backgroundColor: "rgba(47, 184, 198, 0.15)",
                    tension: 0.3,
                },
                {
                    label: "24h rainfall (mm)",
                    data: [],
                    borderColor: "#F2A93B",
                    backgroundColor: "rgba(242, 169, 59, 0.15)",
                    tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#8FA7B8" } },
            },
            scales: {
                x: {
                    ticks: { color: "#8FA7B8" },
                    grid: { color: "rgba(255,255,255,0.06)" },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#8FA7B8" },
                    grid: { color: "rgba(255,255,255,0.06)" },
                    title: { display: true, text: "Rainfall (mm)", color: "#8FA7B8" },
                },
            },
        },
    });
}

function updateChart(rows) {
    const stationName = document.getElementById("selectedStationName")?.textContent || "—";
    const chartStation = document.getElementById("chartStation");
    if (chartStation) chartStation.textContent = stationName;

    rainfallChart.data.labels = rows.map((row) => row.timestamp.slice(5, 16));
    rainfallChart.data.datasets[0].data = rows.map((row) => row.rainfall_1h);
    rainfallChart.data.datasets[1].data = rows.map((row) => row.rainfall_24h);
    rainfallChart.update();
}

function updateHistory(rows) {
    const historyList = document.getElementById("historyList");
    historyList.innerHTML = "";

    if (!rows.length) {
        historyList.textContent = "No history available.";
        return;
    }

    rows.slice().reverse().forEach((row) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.innerHTML = `
            <span>${row.timestamp}</span>
            <span>${row.station || row.region}</span>
            <span>24h: ${row.rainfall_24h} mm</span>
            <span>Flood soon: ${Number(row.flood_soon) === 1 ? "YES" : "NO"}</span>
        `;
        historyList.appendChild(item);
    });
}

async function updateHealth() {
    try {
        const data = await getJson(`${API_BASE}/api/health`);
        document.getElementById("apiStatus").textContent = data.status === "ok" ? "ONLINE" : "OFFLINE";
        document.getElementById("modelStatus").textContent = data.model;
        document.getElementById("dataStatus").textContent = data.data;
        document.getElementById("predictionStatus").textContent = data.prediction;
    } catch (error) {
        document.getElementById("apiStatus").textContent = "OFFLINE";
        document.getElementById("modelStatus").textContent = "ERROR";
        document.getElementById("dataStatus").textContent = "ERROR";
        document.getElementById("predictionStatus").textContent = "ERROR";
    }
}

async function loadStations(region) {
    const stationSelect = document.getElementById("stationSelect");
    if (!stationSelect) return [];

    stationSelect.innerHTML = `<option value="">Loading stations...</option>`;
    stationSelect.disabled = true;

    const data = await getJson(`${API_BASE}/api/stations?region=${encodeURIComponent(region)}`);
    const stations = data.stations || [];

    stationSelect.innerHTML = "";
    if (!stations.length) {
        stationSelect.innerHTML = `<option value="">No stations available</option>`;
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

async function loadStation(station) {
    const region = document.getElementById("regionSelect").value;
    if (!station) return;

    hideMessage();

    try {
        const query = `region=${encodeURIComponent(region)}&station=${encodeURIComponent(station)}`;
        const [risk, rainfall, history, stations] = await Promise.all([
            getJson(`${API_BASE}/api/flood-risk?${query}`),
            getJson(`${API_BASE}/api/rainfall?${query}`),
            getJson(`${API_BASE}/api/history?${query}`),
            getJson(`${API_BASE}/api/stations?region=${encodeURIComponent(region)}`),
        ]);

        updateRiskCard(risk);
        updateFeatures(risk.features);
        updateChart(rainfall.rainfall);
        updateHistory(history.history);
        updateMap(risk, stations.stations);
        await updateHealth();
    } catch (error) {
        showMessage(error.message);
        await updateHealth();
    }
}

async function loadRegion(region) {
    hideMessage();

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

    const regionSelect = document.getElementById("regionSelect");
    const stationSelect = document.getElementById("stationSelect");

    regionSelect.addEventListener("change", () => loadRegion(regionSelect.value));
    stationSelect.addEventListener("change", () => loadStation(stationSelect.value));

    await updateHealth();
    await loadRegion(regionSelect.value);
});