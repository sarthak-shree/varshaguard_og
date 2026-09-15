const API_BASE = "/api/bihar";

const elements = {
    apiStatus: document.getElementById("apiStatus"),
    districtSelect: document.getElementById("districtSelect"),
    refreshButton: document.getElementById("refreshButton"),
    fetchMeta: document.getElementById("fetchMeta"),
    observationCount: document.getElementById("observationCount"),
    risingCount: document.getElementById("risingCount"),
    steadyCount: document.getElementById("steadyCount"),
    fallingCount: document.getElementById("fallingCount"),
    riverTableBody: document.getElementById("riverTableBody"),
    errorCard: document.getElementById("errorCard"),
    errorMessage: document.getElementById("errorMessage"),
};

let allRecords = [];
let selectedDistrict = "";

function setApiStatus(online, label) {
    const dot = elements.apiStatus.querySelector("span:first-child");
    const text = elements.apiStatus.querySelector("span:last-child");
    if (dot) dot.className = online ? "online" : "offline";
    if (text) text.textContent = label;
    elements.apiStatus.classList.toggle("online", online);
    elements.apiStatus.classList.toggle("offline", !online);
}

function showError(message) {
    elements.errorCard.hidden = false;
    elements.errorMessage.textContent = message;
}

function hideError() {
    elements.errorCard.hidden = true;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatNumber(value) {
    return typeof value === "number" ? value.toFixed(2) : "—";
}

function formatObserved(value) {
    return value || "—";
}

function normalizeDistrict(value) {
    return String(value || "").trim().toLowerCase();
}

function populateDistricts(records) {
    const current = selectedDistrict;
    const districts = [...new Set(records
        .map(record => record.district)
        .filter(Boolean))]
        .sort((a, b) => a.localeCompare(b));

    elements.districtSelect.innerHTML = '<option value="">All Bihar</option>';
    for (const district of districts) {
        const option = document.createElement("option");
        option.value = district;
        option.textContent = district;
        option.selected = normalizeDistrict(district) === normalizeDistrict(current);
        elements.districtSelect.appendChild(option);
    }
}

function updateSummary(records) {
    const counts = { rising: 0, steady: 0, falling: 0 };
    for (const record of records) {
        const trend = normalizeDistrict(record.trend);
        if (trend === "rising") counts.rising += 1;
        else if (trend === "steady") counts.steady += 1;
        else if (trend === "falling") counts.falling += 1;
    }

    elements.observationCount.textContent = records.length;
    elements.risingCount.textContent = counts.rising;
    elements.steadyCount.textContent = counts.steady;
    elements.fallingCount.textContent = counts.falling;
}

function renderRecords(records) {
    if (!records.length) {
        elements.riverTableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No river observations match this district.</td></tr>';
        updateSummary(records);
        return;
    }

    const rows = records.map(record => {
        const trend = record.trend || "—";
        const trendClass = trend.toLowerCase();
        return `
            <tr>
                <td>${escapeHtml(record.river)}</td>
                <td>${escapeHtml(record.station)}</td>
                <td>${escapeHtml(record.district)}</td>
                <td>${formatNumber(record.water_level_m)}</td>
                <td>${formatNumber(record.warning_level_m)}</td>
                <td>${formatNumber(record.danger_level_m)}</td>
                <td><span class="trend ${escapeHtml(trendClass)}">${escapeHtml(trend)}</span></td>
                <td>${escapeHtml(formatObserved(record.observed_at))}</td>
            </tr>`;
    }).join("");

    elements.riverTableBody.innerHTML = rows;
    updateSummary(records);
}

function visibleRecords() {
    if (!selectedDistrict) return allRecords;
    const target = normalizeDistrict(selectedDistrict);
    return allRecords.filter(record => normalizeDistrict(record.district) === target);
}

function renderMeta(payload) {
    const mode = payload.cached ? "Cached" : "Fresh";
    const fetched = payload.fetched_at ? new Date(payload.fetched_at).toLocaleString() : "unknown";
    elements.fetchMeta.textContent = `${mode} data • fetched ${fetched} • ${payload.count} observations`;
}

async function loadLiveRivers(forceRefresh = false) {
    hideError();
    setApiStatus(false, "Loading API");
    elements.refreshButton.disabled = true;
    elements.riverTableBody.innerHTML = '<tr><td colspan="8" class="empty-state">Loading live observations...</td></tr>';

    try {
        const params = new URLSearchParams();
        if (forceRefresh) params.set("refresh", "true");
        const url = `${API_BASE}/live-rivers${params.toString() ? `?${params}` : ""}`;
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        const payload = await response.json();

        if (!response.ok || !payload.success) {
            throw new Error(payload.error || `API request failed (${response.status})`);
        }

        allRecords = Array.isArray(payload.records) ? payload.records : [];
        populateDistricts(allRecords);
        renderMeta(payload);
        renderRecords(visibleRecords());
        setApiStatus(true, "Live API connected");
    } catch (error) {
        allRecords = [];
        updateSummary([]);
        elements.riverTableBody.innerHTML = '<tr><td colspan="8" class="empty-state">Live observations could not be loaded.</td></tr>';
        elements.fetchMeta.textContent = "Live data unavailable";
        showError(error instanceof Error ? error.message : "Unable to fetch live Bihar river data.");
        setApiStatus(false, "API unavailable");
    } finally {
        elements.refreshButton.disabled = false;
    }
}

elements.districtSelect.addEventListener("change", event => {
    selectedDistrict = event.target.value;
    renderRecords(visibleRecords());
});

elements.refreshButton.addEventListener("click", () => loadLiveRivers(true));

loadLiveRivers();
