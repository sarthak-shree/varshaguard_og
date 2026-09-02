const API_BASE = "http://127.0.0.1:5001";
let map;
let markerLayer;
let rainfallChart;

const regionCenters = {
    Assam: [26.1445, 91.7362],
    Uttarakhand: [30.3165, 78.0322],
};

function showMessage(text) {
    const message = document.getElementById("message");
    message.textContent = text;
    message.classList.remove("hidden");
}

function hideMessage() {
    document.getElementById("message").classList.add("hidden");
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
    if (risk === "HIGH") {
        return "risk-high";
    }

    if (risk === "MEDIUM") {
        return "risk-medium";
    }

    return "risk-low";
}

function updateRiskCard(data) {
    const card = document.getElementById("riskCard");
    card.className = "risk-card " + riskClassName(data.risk);

    document.getElementById("riskLevel").textContent = data.risk;
    document.getElementById("probability").textContent = Math.round(data.flood_probability * 100) + "%";
    document.getElementById("warning").textContent = data.warning;
    document.getElementById("horizon").textContent = data.prediction_horizon_hours;
}

function updateFeatures(features) {
    const featureList = document.getElementById("featureList");
    featureList.innerHTML = "";

    Object.keys(features).forEach((name) => {
        const item = document.createElement("div");
        item.className = "feature";
        item.innerHTML = `<span>${name}</span><strong>${features[name]}</strong>`;
        featureList.appendChild(item);
    });
}

function updateMap(data, stations) {
    markerLayer.clearLayers();

    const center = [data.latitude, data.longitude];
    map.setView(center, 8);

    L.circleMarker(center, {
        radius: 12,
        color: "white",
        weight: 2,
        fillColor: data.risk === "HIGH" ? "#c93636" : data.risk === "MEDIUM" ? "#c47a10" : "#18895b",
        fillOpacity: 0.9,
    })
        .bindPopup(`${data.region}<br>${data.risk} risk<br>${Math.round(data.flood_probability * 100)}% probability`)
        .addTo(markerLayer);

    stations.forEach((station) => {
        L.marker([station.latitude, station.longitude])
            .bindPopup(station.station)
            .addTo(markerLayer);
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
                    borderColor: "#1976a3",
                    backgroundColor: "rgba(25, 118, 163, 0.12)",
                    tension: 0.3,
                },
                {
                    label: "24h rainfall (mm)",
                    data: [],
                    borderColor: "#c93636",
                    backgroundColor: "rgba(201, 54, 54, 0.12)",
                    tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: "Rainfall (mm)",
                    },
                },
            },
        },
    });
}

function updateChart(rows) {
    rainfallChart.data.labels = rows.map((row) => row.timestamp.slice(5, 16));
    rainfallChart.data.datasets[0].data = rows.map((row) => row.rainfall_1h);
    rainfallChart.data.datasets[1].data = rows.map((row) => row.rainfall_24h);
    rainfallChart.update();
}

function updateHistory(rows) {
    const historyList = document.getElementById("historyList");
    historyList.innerHTML = "";

    rows.forEach((row) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.innerHTML = `
            <span>${row.timestamp}</span>
            <span>${row.station || row.region}</span>
            <span>24h: ${row.rainfall_24h} mm</span>
            <span>Flood soon: ${row.flood_soon}</span>
        `;
        historyList.appendChild(item);
    });
}

async function updateHealth() {
    try {
        const data = await fetch(`${API_BASE}/api/health`).then((response) => response.json());
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

async function loadRegion(region) {
    hideMessage();

    try {
        const risk = await getJson(`${API_BASE}/api/flood-risk?region=${region}`);
        const rainfall = await getJson(`${API_BASE}/api/rainfall?region=${region}`);
        const history = await getJson(`${API_BASE}/api/history?region=${region}`);
        const stations = await getJson(`${API_BASE}/api/stations?region=${region}`);

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

document.addEventListener("DOMContentLoaded", async () => {
    setupMap();
    setupChart();

    const selector = document.getElementById("regionSelect");
    selector.addEventListener("change", () => {
        loadRegion(selector.value);
    });

    await updateHealth();
    await loadRegion(selector.value);
});
