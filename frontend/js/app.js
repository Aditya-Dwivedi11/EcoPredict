"use strict";

// ==================================================
// EcoPredict Dashboard Configuration
// ==================================================

const API_BASE = window.location.origin;

const LAYER_DESCRIPTIONS = {
    before: "Earlier satellite observation.",
    after: "Later satellite observation.",
    difference: "Change in vegetation greenness between periods."
};

const LAYER_LABELS = {
    before: "Before",
    after: "After",
    difference: "Difference"
};

const LAYER_STYLES = {
    before: {
        low: "Low vegetation",
        high: "High vegetation"
    },
    after: {
        low: "Low vegetation",
        high: "High vegetation"
    },
    difference: {
        low: "Decrease",
        high: "Increase"
    }
};

// ==================================================
// Global Variables
// ==================================================

let map = null;
let rasterOverlay = null;
let currentLayer = null;
let rasterMetadata = null;
let rasterRequestId = 0;

let drawnItems = null;
let selectedStudyBounds = null;
let searchMarker = null;
let userNavigatedMap = false;
let analysisInProgress = false;


// ==================================================
// Initialize Leaflet Map
// ==================================================

function initializeMap() {

    map = L.map("map", {
        zoomControl: true,
        preferCanvas: true,
        zoomSnap: 0.25,
        zoomDelta: 0.25
    });

    L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
            attribution: "Tiles &copy; Esri",
            maxZoom: 19
        }
    ).addTo(map);

    map.setView([26.47, 80.32], 11);

    requestAnimationFrame(() => {
        map.invalidateSize(true);
    });

    initializeStudyAreaDrawing();
}


// ==================================================
// Dashboard Status
// ==================================================

function updateStatus(message, isError = false) {

    const status = document.getElementById("system-status");

    if (!status) return;

    status.textContent = message;

    status.style.color = isError
        ? "#f16b70"
        : "#36c98f";
}


function updateAnalysisMessage(message, isError = false) {

    const element = document.getElementById("analysis-message");

    if (!element) return;

    element.textContent = message;

    element.style.color = isError
        ? "#f16b70"
        : "#36c98f";
}


// ==================================================
// Geographic Bounds
// ==================================================

function getLayerBounds(layer) {

    const bounds = rasterMetadata.layers[layer].bounds;

    return [
        [bounds.south, bounds.west],
        [bounds.north, bounds.east]
    ];
}


// ==================================================
// Load NDVI Raster Metadata
// ==================================================

async function loadMetadata(forceFit = false) {

    updateStatus("Loading satellite metadata...");

    try {

        const response = await fetch(
            `${API_BASE}/api/v1/ndvi-rasters/metadata`,
            {
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                `Metadata API returned HTTP ${response.status}`
            );
        }

        const newMetadata = await response.json();

        if (
            !newMetadata.layers ||
            !newMetadata.layers.before ||
            !newMetadata.layers.after ||
            !newMetadata.layers.difference
        ) {
            throw new Error("Invalid raster metadata structure.");
        }

        rasterMetadata = newMetadata;

        updateDashboardMetrics();
        updatePeriods();

        const bounds = getLayerBounds("before");

        await new Promise(resolve => {

            requestAnimationFrame(() => {

                map.invalidateSize(true);

                if (forceFit || !userNavigatedMap) {

                    map.fitBounds(bounds, {
                        padding: [30, 30],
                        maxZoom: 15,
                        animate: false
                    });
                }

                console.log(
                    "EcoPredict raster metadata:",
                    rasterMetadata
                );

                console.log("Raster bounds:", bounds);

                resolve();
            });
        });

        await changeRasterLayer("before");

    } catch (error) {

        console.error(
            "Metadata loading failed:",
            error
        );

        updateStatus(
            "Unable to load satellite metadata",
            true
        );

        throw error;
    }
}


// ==================================================
// Update NDVI Statistics
// ==================================================

function updateDashboardMetrics() {

    const before = rasterMetadata.layers.before;
    const after = rasterMetadata.layers.after;
    const difference = rasterMetadata.layers.difference;

    document.getElementById("before-ndvi").textContent =
        Number(before.mean).toFixed(4);

    document.getElementById("after-ndvi").textContent =
        Number(after.mean).toFixed(4);

    const change = Number(after.mean) - Number(before.mean);

    const changeElement =
        document.getElementById("ndvi-change");

    changeElement.textContent =
        `${change > 0 ? "+" : ""}${change.toFixed(4)}`;

    changeElement.style.color =
        change < 0
            ? "#f16b70"
            : "#36c98f";

    document.getElementById("valid-pixels").textContent =
        Number(
            difference.valid_pixel_count
        ).toLocaleString();
}


// ==================================================
// Display Analysis Periods
// ==================================================

function updatePeriods() {

    document.getElementById("before-period").textContent =
        formatPeriod(rasterMetadata.before_period);

    document.getElementById("after-period").textContent =
        formatPeriod(rasterMetadata.after_period);
}


function formatPeriod(period) {

    if (!period) {
        return "Not available";
    }

    if (Array.isArray(period)) {
        return period.join(" to ");
    }

    if (typeof period === "object") {

        const start = period.start || period.start_date;
        const end = period.end || period.end_date;

        if (start && end) {
            return `${start} to ${end}`;
        }

        return JSON.stringify(period);
    }

    return String(period);
}


// ==================================================
// Load Satellite Raster Layer
// ==================================================

async function changeRasterLayer(layer) {

    if (
        !rasterMetadata ||
        !LAYER_LABELS[layer]
    ) {
        return;
    }

    const requestId = ++rasterRequestId;

    const bounds = getLayerBounds(layer);

    const imageUrl =
        `${API_BASE}/api/v1/ndvi-rasters/${layer}.png`;

    updateStatus(`Loading ${layer} satellite layer...`);

    try {

        const response = await fetch(
            imageUrl,
            {
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                `Raster API returned HTTP ${response.status}`
            );
        }

        const imageBlob = await response.blob();

        if (requestId !== rasterRequestId) {
            return;
        }

        if (!imageBlob.type.includes("image/png")) {
            throw new Error("Raster API did not return a PNG image.");
        }

        const imageObjectUrl =
            URL.createObjectURL(imageBlob);

        const newOverlay = L.imageOverlay(
            imageObjectUrl,
            bounds,
            {
                opacity: 0.85,
                interactive: false
            }
        );

        newOverlay.once("load", () => {

            if (requestId !== rasterRequestId) {
                URL.revokeObjectURL(imageObjectUrl);
                return;
            }

            if (rasterOverlay) {

                map.removeLayer(rasterOverlay);

                if (rasterOverlay._ecopredictUrl) {
                    URL.revokeObjectURL(
                        rasterOverlay._ecopredictUrl
                    );
                }
            }

            rasterOverlay = newOverlay;

            rasterOverlay._ecopredictUrl =
                imageObjectUrl;

            currentLayer = layer;

            updateLayerInterface(layer);

            updateStatus("Satellite data connected");

            console.log(
                `EcoPredict ${layer} raster loaded`,
                {
                    imageSize: imageBlob.size,
                    bounds: bounds
                }
            );
        });

        newOverlay.once("error", () => {

            URL.revokeObjectURL(imageObjectUrl);

            if (requestId === rasterRequestId) {
                updateStatus(
                    "Satellite raster could not be displayed",
                    true
                );
            }
        });

        newOverlay.addTo(map);

    } catch (error) {

        console.error(
            "Raster loading failed:",
            error
        );

        if (requestId === rasterRequestId) {
            updateStatus(
                "Unable to load satellite raster",
                true
            );
        }

        throw error;
    }
}


// ==================================================
// Update Layer Interface
// ==================================================

function updateLayerInterface(layer) {

    currentLayer = layer;

    document.querySelectorAll(".layer-button").forEach(button => {

        button.classList.toggle(
            "active",
            button.dataset.layer === layer
        );
    });

    document.getElementById("map-layer-label").textContent =
        LAYER_LABELS[layer];

    document.getElementById("layer-description").textContent =
        LAYER_DESCRIPTIONS[layer];

    const legend = document.querySelector(".map-legend");

    legend.innerHTML = `
        <span class="legend-low"></span>
        ${LAYER_STYLES[layer].low}
        <span class="legend-high"></span>
        ${LAYER_STYLES[layer].high}
    `;
}


// ==================================================
// Layer Controls
// ==================================================

function setupLayerControls() {

    document.querySelectorAll(".layer-button").forEach(button => {

        button.addEventListener("click", () => {

            const layer = button.dataset.layer;

            if (layer !== currentLayer) {
                changeRasterLayer(layer).catch(error => {
                    console.error(error);
                });
            }
        });
    });
}


// ==================================================
// Location Search
// ==================================================

function setupLocationSearch() {

    const searchInput =
        document.getElementById("region-search");

    const searchButton =
        document.getElementById("search-button");

    if (!searchInput || !searchButton) {

        console.warn(
            "Location search elements were not found."
        );

        return;
    }

    searchButton.addEventListener("click", searchLocation);

    searchInput.addEventListener("keydown", event => {

        if (event.key === "Enter") {
            event.preventDefault();
            searchLocation();
        }
    });
}


async function searchLocation() {

    const searchInput =
        document.getElementById("region-search");

    const query = searchInput.value.trim();

    if (!query) {

        updateStatus("Enter a location to search.", true);

        return;
    }

    updateStatus(`Searching for ${query}...`);

    const searchButton =
        document.getElementById("search-button");

    searchButton.disabled = true;

    try {

        const parameters = new URLSearchParams({
            q: query,
            format: "jsonv2",
            limit: "1"
        });

        const response = await fetch(
            `https://nominatim.openstreetmap.org/search?${parameters.toString()}`,
            {
                headers: {
                    "Accept": "application/json",
                    "Accept-Language": "en"
                }
            }
        );

        if (!response.ok) {
            throw new Error(
                `Location search returned HTTP ${response.status}`
            );
        }

        const results = await response.json();

        if (!results.length) {

            updateStatus(
                "Location not found. Try another search.",
                true
            );

            return;
        }

        const result = results[0];

        const latitude = Number(result.lat);
        const longitude = Number(result.lon);

        if (
            !Number.isFinite(latitude) ||
            !Number.isFinite(longitude)
        ) {
            throw new Error("Invalid coordinates received.");
        }

        clearStudyArea();

        userNavigatedMap = true;

        if (result.boundingbox) {

            const south = Number(result.boundingbox[0]);
            const north = Number(result.boundingbox[1]);
            const west = Number(result.boundingbox[2]);
            const east = Number(result.boundingbox[3]);

            if (
                [south, north, west, east].every(Number.isFinite)
            ) {

                map.fitBounds(
                    [
                        [south, west],
                        [north, east]
                    ],
                    {
                        padding: [30, 30],
                        maxZoom: 14
                    }
                );

            } else {

                map.setView([latitude, longitude], 12);
            }

        } else {

            map.setView([latitude, longitude], 12);
        }

        if (searchMarker) {
            map.removeLayer(searchMarker);
        }

        searchMarker = L.marker(
            [latitude, longitude]
        ).addTo(map);

        searchMarker.bindPopup(
            `<strong>${escapeHTML(result.display_name)}</strong>`
        ).openPopup();

        const locationLabel =
            document.getElementById("location-label");

        if (locationLabel) {
            locationLabel.textContent = result.display_name;
        }

        updateStatus(
            "Location found. Draw a rectangle to select your study area."
        );

        console.log("Location search result:", result);

    } catch (error) {

        console.error(
            "Location search failed:",
            error
        );

        updateStatus(
            "Location search failed. Check your internet connection.",
            true
        );

    } finally {

        searchButton.disabled = false;
    }
}


// ==================================================
// Safe HTML Text
// ==================================================

function escapeHTML(value) {

    return String(value).replace(/[&<>"']/g, character => {

        const replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        };

        return replacements[character];
    });
}


// ==================================================
// Study Area Drawing Controls
// ==================================================

function initializeStudyAreaDrawing() {

    if (!L.Control.Draw) {

        console.error(
            "Leaflet Draw is not loaded."
        );

        updateStatus(
            "Drawing tools unavailable. Check Leaflet Draw.",
            true
        );

        return;
    }

    drawnItems = new L.FeatureGroup();

    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({

        position: "topright",

        draw: {

            rectangle: {
                shapeOptions: {
                    color: "#36c98f",
                    weight: 2,
                    fillOpacity: 0.12
                }
            },

            polygon: false,
            polyline: false,
            circle: false,
            circlemarker: false,
            marker: false
        },

        edit: {

            featureGroup: drawnItems,

            edit: true,
            remove: true
        }
    });

    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, event => {

        drawnItems.clearLayers();

        const layer = event.layer;

        drawnItems.addLayer(layer);

        userNavigatedMap = true;

        updateSelectedStudyArea(layer.getBounds());
    });

    map.on(L.Draw.Event.EDITED, event => {

        event.layers.eachLayer(layer => {
            updateSelectedStudyArea(layer.getBounds());
        });
    });

    map.on(L.Draw.Event.DELETED, () => {

        selectedStudyBounds = null;

        updateStatus(
            "Study area cleared. Draw a new rectangle."
        );

        updateAnalysisMessage(
            "Draw a rectangle before running analysis."
        );

        console.log("Study area selection cleared.");
    });

    console.log("EcoPredict study-area drawing initialized.");
}


// ==================================================
// Update Selected Study Area
// ==================================================

function updateSelectedStudyArea(bounds) {

    selectedStudyBounds = {

        south: Number(bounds.getSouth().toFixed(6)),
        west: Number(bounds.getWest().toFixed(6)),
        north: Number(bounds.getNorth().toFixed(6)),
        east: Number(bounds.getEast().toFixed(6))
    };

    updateStatus("Study area selected successfully.");

    updateAnalysisMessage(
        "Study area selected. Choose dates and run analysis."
    );

    console.log(
        "Selected EcoPredict study area:",
        selectedStudyBounds
    );

    console.log(
        "Selected area coordinates:",
        {
            southwest: [
                selectedStudyBounds.south,
                selectedStudyBounds.west
            ],

            northeast: [
                selectedStudyBounds.north,
                selectedStudyBounds.east
            ]
        }
    );
}


// ==================================================
// Clear Study Area
// ==================================================

function clearStudyArea() {

    if (drawnItems) {
        drawnItems.clearLayers();
    }

    selectedStudyBounds = null;
}


// ==================================================
// Public Study Area Access
// ==================================================

window.EcoPredictStudyArea = {

    getBounds: function () {

        if (!selectedStudyBounds) {
            return null;
        }

        return { ...selectedStudyBounds };
    },

    clear: function () {

        clearStudyArea();

        updateStatus("Study area cleared.");
    }
};


// ==================================================
// Date Input Setup
// ==================================================

function setupDateInputs() {

    const dateIds = [
        "before-start",
        "before-end",
        "after-start",
        "after-end"
    ];

    const inputs = dateIds.map(id =>
        document.getElementById(id)
    );

    if (inputs.some(input => !input)) {

        console.warn(
            "One or more analysis date inputs are missing."
        );

        return;
    }

    // Default example periods.
    // Users can change these dates before analysis.
    const defaults = {
        "before-start": "2024-10-01",
        "before-end": "2024-11-01",
        "after-start": "2025-10-01",
        "after-end": "2025-11-01"
    };

    Object.entries(defaults).forEach(([id, value]) => {

        const input = document.getElementById(id);

        if (!input.value) {
            input.value = value;
        }
    });
}


// ==================================================
// Safe HTML Text
// ==================================================

function escapeHTML(value) {

    return String(value).replace(/[&<>"']/g, character => {

        const replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        };

        return replacements[character];
    });
}


// ==================================================
// Study Area Drawing Controls
// ==================================================

function initializeStudyAreaDrawing() {

    if (!L.Control.Draw) {

        console.error(
            "Leaflet Draw is not loaded."
        );

        updateStatus(
            "Drawing tools unavailable. Check Leaflet Draw.",
            true
        );

        return;
    }

    drawnItems = new L.FeatureGroup();

    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({

        position: "topright",

        draw: {

            rectangle: {
                shapeOptions: {
                    color: "#36c98f",
                    weight: 2,
                    fillOpacity: 0.12
                }
            },

            polygon: false,
            polyline: false,
            circle: false,
            circlemarker: false,
            marker: false
        },

        edit: {

            featureGroup: drawnItems,

            edit: true,
            remove: true
        }
    });

    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, event => {

        drawnItems.clearLayers();

        const layer = event.layer;

        drawnItems.addLayer(layer);

        userNavigatedMap = true;

        updateSelectedStudyArea(layer.getBounds());
    });

    map.on(L.Draw.Event.EDITED, event => {

        event.layers.eachLayer(layer => {
            updateSelectedStudyArea(layer.getBounds());
        });
    });

    map.on(L.Draw.Event.DELETED, () => {

        selectedStudyBounds = null;

        updateStatus(
            "Study area cleared. Draw a new rectangle."
        );

        updateAnalysisMessage(
            "Draw a rectangle before running analysis."
        );

        console.log("Study area selection cleared.");
    });

    console.log("EcoPredict study-area drawing initialized.");
}


// ==================================================
// Update Selected Study Area
// ==================================================

function updateSelectedStudyArea(bounds) {

    selectedStudyBounds = {

        south: Number(bounds.getSouth().toFixed(6)),
        west: Number(bounds.getWest().toFixed(6)),
        north: Number(bounds.getNorth().toFixed(6)),
        east: Number(bounds.getEast().toFixed(6))
    };

    updateStatus("Study area selected successfully.");

    updateAnalysisMessage(
        "Study area selected. Choose dates and run analysis."
    );

    console.log(
        "Selected EcoPredict study area:",
        selectedStudyBounds
    );

    console.log(
        "Selected area coordinates:",
        {
            southwest: [
                selectedStudyBounds.south,
                selectedStudyBounds.west
            ],

            northeast: [
                selectedStudyBounds.north,
                selectedStudyBounds.east
            ]
        }
    );
}


// ==================================================
// Clear Study Area
// ==================================================

function clearStudyArea() {

    if (drawnItems) {
        drawnItems.clearLayers();
    }

    selectedStudyBounds = null;
}


// ==================================================
// Public Study Area Access
// ==================================================

window.EcoPredictStudyArea = {

    getBounds: function () {

        if (!selectedStudyBounds) {
            return null;
        }

        return { ...selectedStudyBounds };
    },

    clear: function () {

        clearStudyArea();

        updateStatus("Study area cleared.");
    }
};


// ==================================================
// Date Input Setup
// ==================================================

function setupDateInputs() {

    const dateIds = [
        "before-start",
        "before-end",
        "after-start",
        "after-end"
    ];

    const inputs = dateIds.map(id =>
        document.getElementById(id)
    );

    if (inputs.some(input => !input)) {

        console.warn(
            "One or more analysis date inputs are missing."
        );

        return;
    }

    // Default example periods.
    // Users can change these dates before analysis.
    const defaults = {
        "before-start": "2024-10-01",
        "before-end": "2024-11-01",
        "after-start": "2025-10-01",
        "after-end": "2025-11-01"
    };

    Object.entries(defaults).forEach(([id, value]) => {

        const input = document.getElementById(id);

        if (!input.value) {
            input.value = value;
        }
    });
}


// ==================================================
// Validate Analysis Inputs
// ==================================================

function getAnalysisRequest() {

    if (!selectedStudyBounds) {

        throw new Error(
            "Please draw a rectangle to select your study area."
        );
    }

    const beforeStart =
        document.getElementById("before-start").value;

    const beforeEnd =
        document.getElementById("before-end").value;

    const afterStart =
        document.getElementById("after-start").value;

    const afterEnd =
        document.getElementById("after-end").value;

    if (
        !beforeStart ||
        !beforeEnd ||
        !afterStart ||
        !afterEnd
    ) {

        throw new Error(
            "Please select all four analysis dates."
        );
    }

    const beforeStartDate = new Date(
        `${beforeStart}T00:00:00Z`
    );

    const beforeEndDate = new Date(
        `${beforeEnd}T00:00:00Z`
    );

    const afterStartDate = new Date(
        `${afterStart}T00:00:00Z`
    );

    const afterEndDate = new Date(
        `${afterEnd}T00:00:00Z`
    );

    if (
        beforeStartDate > beforeEndDate ||
        afterStartDate > afterEndDate
    ) {

        throw new Error(
            "Each period's start date must be before or equal to its end date."
        );
    }

    if (beforeEndDate > afterStartDate) {

        throw new Error(
            "The Before period must end on or before the After period starts."
        );
    }

    return {

        west: selectedStudyBounds.west,
        south: selectedStudyBounds.south,
        east: selectedStudyBounds.east,
        north: selectedStudyBounds.north,

        before_start: beforeStart,
        before_end: beforeEnd,

        after_start: afterStart,
        after_end: afterEnd
    };
}


// ==================================================
// Run Satellite Analysis
// ==================================================

function setupAnalysisControls() {

    const button =
        document.getElementById("run-analysis-button");

    if (!button) {

        console.warn(
            "Run Analysis button was not found."
        );

        return;
    }

    button.addEventListener("click", runSatelliteAnalysis);
}


async function runSatelliteAnalysis() {

    if (analysisInProgress) return;

    const button = document.getElementById("run-analysis-button");
    let requestData;

    try {
        requestData = getAnalysisRequest();
    } catch (error) {
        updateAnalysisMessage(error.message, true);
        updateStatus("Analysis input validation failed.", true);
        return;
    }

    analysisInProgress = true;
    button.disabled = true;
    button.textContent = "Submitting Analysis...";

    updateAnalysisMessage(
        "Submitting satellite analysis. The map will update automatically when processing is complete."
    );
    updateStatus("Submitting satellite analysis...");

    async function readJsonResponse(response) {
        const responseText = await response.text();

        if (!responseText) return {};

        try {
            return JSON.parse(responseText);
        } catch {
            throw new Error(
                `Server returned an invalid response (HTTP ${response.status}).`
            );
        }
    }

    const wait = milliseconds =>
        new Promise(resolve => setTimeout(resolve, milliseconds));

    try {
        // Submit analysis request
        const submitResponse = await fetch(
            `${API_BASE}/api/v1/ndvi-analysis`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(requestData)
            }
        );

        const submission = await readJsonResponse(submitResponse);

        if (!submitResponse.ok) {
            const detail = typeof submission.detail === "string"
                ? submission.detail
                : JSON.stringify(submission.detail);

            throw new Error(
                detail || `Analysis submission failed with HTTP ${submitResponse.status}.`
            );
        }

        if (!submission.job_id) {
            throw new Error("The server did not return an analysis job ID.");
        }

        const jobId = submission.job_id;

        console.log("EcoPredict analysis job submitted:", submission);

        updateAnalysisMessage(
            "Analysis queued. Waiting for satellite processing to start..."
        );
        updateStatus("Satellite analysis queued...");

        // Poll the backend for job status
        const pollingInterval = 3000;
        const maximumWait = 30 * 60 * 1000;
        const startedAt = Date.now();

        while (Date.now() - startedAt < maximumWait) {

            await wait(pollingInterval);

            const statusResponse = await fetch(
                `${API_BASE}/api/v1/ndvi-analysis/${encodeURIComponent(jobId)}`,
                {
                    cache: "no-store"
                }
            );

            const job = await readJsonResponse(statusResponse);

            if (!statusResponse.ok) {
                const detail = typeof job.detail === "string"
                    ? job.detail
                    : JSON.stringify(job.detail);

                throw new Error(
                    detail || `Could not check analysis status (HTTP ${statusResponse.status}).`
                );
            }

            console.log("EcoPredict analysis job status:", job);

            // Job is waiting in queue
            if (job.status === "queued") {

                updateAnalysisMessage(
                    "Analysis is queued and will start shortly..."
                );

                updateStatus("Satellite analysis queued...");
                button.textContent = "Analysis Queued...";

                continue;
            }

            // Job is currently processing
            if (job.status === "running") {

                updateAnalysisMessage(
                    "Satellite analysis is running. This may take several minutes; please keep this page open."
                );

                updateStatus("Processing satellite imagery...");
                button.textContent = "Processing Satellite Data...";

                continue;
            }

            // Job failed
            if (job.status === "failed") {
                throw new Error(
                    job.error || "Satellite analysis failed on the server."
                );
            }

            // Job completed successfully
            if (job.status === "completed") {

                console.log(
                    "EcoPredict analysis completed:",
                    job.result
                );

                updateAnalysisMessage(
                    "Satellite analysis completed. Refreshing map and statistics..."
                );

                updateStatus("Refreshing satellite maps...");

                await loadMetadata(true);

                updateAnalysisMessage(
                    "Analysis completed successfully. NDVI maps and statistics have been updated."
                );

                updateStatus(
                    "New satellite analysis completed successfully."
                );

                return;
            }

            throw new Error(
                `The server returned an unknown analysis status: ${job.status || "missing status"}.`
            );
        }

        throw new Error(
            "Analysis is taking longer than 30 minutes. Check the server logs before submitting another analysis."
        );

    } catch (error) {

        console.error(
            "Satellite analysis failed:",
            error
        );

        updateAnalysisMessage(
            `Analysis failed: ${error.message}`,
            true
        );

        updateStatus(
            "Satellite analysis failed. Check the error message.",
            true
        );

    } finally {

        analysisInProgress = false;

        button.disabled = false;

        button.textContent = "Run Satellite Analysis";
    }
}



// ==================================================
// Environmental Analysis
// ==================================================

let environmentalAnalysisInProgress = false;


function setupEnvironmentalControls() {

    const button = document.getElementById(
        "run-environmental-button"
    );

    const startInput = document.getElementById(
        "environmental-start-date"
    );

    const endInput = document.getElementById(
        "environmental-end-date"
    );

    if (!button || !startInput || !endInput) {
        console.warn("Environmental analysis controls not found.");
        return;
    }

    // Default environmental analysis period.
    startInput.value = "2024-10-01";
    endInput.value = "2024-11-01";

    button.addEventListener(
        "click",
        runEnvironmentalAnalysis
    );
}


function updateEnvironmentalMessage(message, isError = false) {

    const element = document.getElementById(
        "environmental-message"
    );

    element.textContent = message;

    element.style.color = isError
        ? "var(--danger)"
        : "var(--text-secondary)";
}



function displayEnvironmentalResult(result, interpretation = {}) {

    const getElement = (id) => document.getElementById(id);

    const setText = (id, value) => {
        const element = getElement(id);
        if (element) {
            element.textContent = value ?? "--";
        }
    };

    const indicatorElement = getElement("environmental-indicator");
    const meanElement = getElement("environmental-mean");
    const countElement = getElement("environmental-image-count");

    indicatorElement.textContent = result.indicator || "--";
    countElement.textContent = result.image_count ?? "--";

    // Existing measurement display
    const noData =
        result.status === "no_data" ||
        result.mean === null ||
        result.mean === undefined ||
        result.image_count === 0;

    let value = null;
    let unit = result.unit || "";

    if (!noData) {

        if (result.hazard === "heatwave") {
            value = Number(result.mean_celsius).toFixed(2);
                        unit = "°C";

        } else if (result.hazard === "air_pollution") {
            value = Number(result.mean).toExponential(3);

        } else if (result.hazard === "flood") {
            value = Number(result.mean).toFixed(2);

        } else {
            value = Number(result.mean).toFixed(4);
        }

        meanElement.textContent = `${value} ${unit}`;

    } else {
        meanElement.textContent = "No data";
    }

    // Environmental Insights
    setText(
        "environmental-headline",
        interpretation.headline || "Analysis completed"
    );

    setText(
        "environmental-plain-language",
        interpretation.plain_language || "No interpretation available."
    );

    setText(
        "environmental-why-it-matters",
        interpretation.why_it_matters
    );

    setText(
        "environmental-what-to-watch",
        interpretation.what_to_watch
    );

    setText(
        "environmental-suggested-action",
        interpretation.suggested_action
    );

    const evidenceStatus = noData
        ? "Insufficient satellite observations"
        : interpretation.evidence_status || "Measurement only";

    setText(
        "environmental-evidence-status",
        `Evidence status: ${evidenceStatus.replaceAll("_", " ")}`
    );

    // Scientific Evidence
    const scientific = interpretation.scientific || {};

    setText(
        "environmental-dataset",
        scientific.dataset || result.dataset
    );

    setText(
        "environmental-scientific-indicator",
        scientific.indicator || result.indicator
    );

    let scientificMeasurement = "No valid measurement";

    if (!noData) {
        if (result.hazard === "heatwave") {
            scientificMeasurement =
                `${Number(result.mean_celsius).toFixed(2)} °C (land surface temperature)`;
        } else if (result.hazard === "air_pollution") {
            scientificMeasurement =
                `${Number(result.mean).toExponential(3)} ${result.unit || ""}`;
        } else if (result.hazard === "flood") {
            scientificMeasurement =
                `${Number(result.mean).toFixed(2)} ${result.unit || ""}`;
        } else {
            scientificMeasurement =
                `${Number(result.mean).toFixed(4)} ${result.unit || ""}`;
        }
    }

    setText(
        "environmental-scientific-value",
        scientificMeasurement
    );

    const startDate = scientific.start_date || result.start_date || "--";
    const endDate = scientific.end_date || result.end_date || "--";

    setText(
        "environmental-observation-period",
        `${startDate} to ${endDate}`
    );

    setText(
        "environmental-scientific-image-count",
        result.image_count ?? "--"
    );

    setText(
        "environmental-limitations",
        interpretation.limitations ||
        "This measurement is not a validated hazard-risk prediction."
    );

    // Status message
    if (noData) {
        updateEnvironmentalMessage(
            result.message || "No valid satellite measurements found."
        );
        return;
    }

    if (result.status !== "ok") {
        throw new Error(
            "The server returned an invalid measurement status."
        );
    }

    updateEnvironmentalMessage(
        `Analysis completed. ${result.image_count} satellite images processed.`
    );
}



async function displayEnvironmentalMap(hazard, requestData) {
    const requestId = ++rasterRequestId;

    const labels = {
        air_pollution: {
            title: "NO₂ Column Density",
            description: "Sentinel-5P tropospheric nitrogen dioxide column density.",
            low: "Lower NO₂",
            high: "Higher NO₂"
        },
        flood: {
            title: "Sentinel-1 VV Backscatter",
            description: "Sentinel-1 radar VV backscatter. This is not a confirmed flood map.",
            low: "Lower backscatter",
            high: "Higher backscatter"
        },
        heatwave: {
            title: "Land Surface Temperature",
            description: "MODIS daytime land-surface temperature in °C, not air temperature.",
            low: "Cooler surface",
            high: "Warmer surface"
        },
        deforestation: {
            title: "Vegetation Greenness (NDVI)",
            description: "Sentinel-2 vegetation greenness. This does not independently confirm deforestation.",
            low: "Lower NDVI",
            high: "Higher NDVI"
        }
    };

    try {
        updateStatus("Rendering environmental satellite map...");

        const response = await fetch(
            `${API_BASE}/api/v1/environmental-map.png`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(requestData),
                cache: "no-store"
            }
        );

        if (!response.ok) {
            let message = "Environmental map rendering failed.";

            try {
                const errorData = await response.json();
                message = errorData.detail || message;
            } catch {
                // Keep the default error message.
            }

            throw new Error(message);
        }

        const imageBlob = await response.blob();

        if (requestId !== rasterRequestId) return;

        if (!imageBlob.type.includes("image/png")) {
            throw new Error("Environmental map response is not a PNG.");
        }

        const west = Number(response.headers.get("X-Raster-West"));
        const south = Number(response.headers.get("X-Raster-South"));
        const east = Number(response.headers.get("X-Raster-East"));
        const north = Number(response.headers.get("X-Raster-North"));

        if (![west, south, east, north].every(Number.isFinite)) {
            throw new Error("Environmental map geographic bounds are missing.");
        }

        const imageUrl = URL.createObjectURL(imageBlob);

        const newOverlay = L.imageOverlay(
            imageUrl,
            [[south, west], [north, east]],
            {
                opacity: 0.85,
                interactive: false
            }
        );

        await new Promise((resolve, reject) => {
            newOverlay.once("load", resolve);
            newOverlay.once("error", reject);
            newOverlay.addTo(map);
        });

        if (requestId !== rasterRequestId) {
            map.removeLayer(newOverlay);
            URL.revokeObjectURL(imageUrl);
            return;
        }

        // Zoom the map to the selected environmental study area.
        // This prevents the raster from appearing as a small rectangle
        // inside a much larger map view.
        map.fitBounds(newOverlay.getBounds(), {
            padding: [35, 35],
            maxZoom: 13,
            animate: true
        });

        if (rasterOverlay) {
            map.removeLayer(rasterOverlay);

            if (rasterOverlay._ecopredictUrl) {
                URL.revokeObjectURL(rasterOverlay._ecopredictUrl);
            }
        }

        rasterOverlay = newOverlay;
        rasterOverlay._ecopredictUrl = imageUrl;
        currentLayer = `environmental-${hazard}`;

        document.querySelectorAll(".layer-button").forEach(button => {
            button.classList.remove("active");
        });

        const config = labels[hazard];

        document.getElementById("map-layer-label").textContent =
            config.title;

        document.getElementById("layer-description").textContent =
            config.description;

        document.querySelector(".map-legend").innerHTML = `
            <span class="legend-low"></span>
            ${config.low}
            <span class="legend-high"></span>
            ${config.high}
        `;

        updateStatus("Environmental satellite map displayed");

        console.log("Environmental map displayed:", hazard);

    } catch (error) {
        console.error("Environmental map failed:", error);
        updateStatus(
            `Environmental measurements loaded, but map rendering failed: ${error.message}`,
            true
        );
    }
}

async function runEnvironmentalAnalysis() {

    if (environmentalAnalysisInProgress) return;

    const button = document.getElementById(
        "run-environmental-button"
    );

    const hazard = document.getElementById(
        "environmental-hazard"
    ).value;

    const startDate = document.getElementById(
        "environmental-start-date"
    ).value;

    const endDate = document.getElementById(
        "environmental-end-date"
    ).value;

    // Validate study area.
    if (!selectedStudyBounds) {

        updateEnvironmentalMessage(
            "Please draw a rectangle to select your study area.",
            true
        );

        return;
    }

    // Validate dates.
    if (!startDate || !endDate) {

        updateEnvironmentalMessage(
            "Please select both analysis dates.",
            true
        );

        return;
    }

    if (new Date(`${startDate}T00:00:00Z`) >
        new Date(`${endDate}T00:00:00Z`)) {

        updateEnvironmentalMessage(
            "Start date must be before or equal to end date.",
            true
        );

        return;
    }

    const requestData = {
        hazard: hazard,

        west: selectedStudyBounds.west,
        south: selectedStudyBounds.south,
        east: selectedStudyBounds.east,
        north: selectedStudyBounds.north,

        start_date: startDate,
        end_date: endDate
    };

    environmentalAnalysisInProgress = true;

    button.disabled = true;
    button.textContent = "Submitting...";

    updateEnvironmentalMessage(
        "Submitting environmental analysis..."
    );

    // Clear previous measurements.
    document.getElementById(
        "environmental-indicator"
    ).textContent = "--";

    document.getElementById(
        "environmental-mean"
    ).textContent = "--";

    document.getElementById(
        "environmental-image-count"
    ).textContent = "--";


    async function readJsonResponse(response) {

        const responseText = await response.text();

        if (!responseText) return {};

        try {
            return JSON.parse(responseText);
        } catch {
            throw new Error(
                `Invalid server response (HTTP ${response.status}).`
            );
        }
    }


    const wait = milliseconds =>
        new Promise(resolve => setTimeout(resolve, milliseconds));


    try {

        // Submit environmental analysis.
        const submitResponse = await fetch(
            `${API_BASE}/api/v1/environmental-analysis`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify(requestData)
            }
        );

        const submission = await readJsonResponse(
            submitResponse
        );

        if (!submitResponse.ok) {

            throw new Error(
                submission.detail ||
                `Submission failed with HTTP ${submitResponse.status}.`
            );
        }

        if (!submission.job_id) {
            throw new Error("Server did not return a job ID.");
        }

        const jobId = submission.job_id;

        console.log(
            "Environmental analysis submitted:",
            submission
        );

        updateEnvironmentalMessage(
            "Analysis queued. Waiting for satellite processing..."
        );

        // Poll job status.
        const pollingInterval = 3000;
        const maximumWait = 30 * 60 * 1000;
        const startedAt = Date.now();

        while (Date.now() - startedAt < maximumWait) {

            await wait(pollingInterval);

            const statusResponse = await fetch(
                `${API_BASE}/api/v1/environmental-analysis/${encodeURIComponent(jobId)}`,
                {
                    cache: "no-store"
                }
            );

            const job = await readJsonResponse(
                statusResponse
            );

            if (!statusResponse.ok) {

                throw new Error(
                    job.detail ||
                    `Could not check job status (HTTP ${statusResponse.status}).`
                );
            }

            console.log(
                "Environmental analysis status:",
                job
            );

            if (job.status === "queued") {

                button.textContent = "Queued...";

                updateEnvironmentalMessage(
                    "Analysis is queued and will start shortly..."
                );

                continue;
            }

            if (job.status === "running") {

                button.textContent = "Processing...";

                updateEnvironmentalMessage(
                    "Processing satellite imagery. This may take several minutes..."
                );

                continue;
            }

            if (job.status === "failed") {

                throw new Error(
                    job.error || "Environmental analysis failed."
                );
            }

            if (job.status === "completed") {

                const result = job.result;

                if (!result || !result.data) {
                    throw new Error(
                        "The server returned an incomplete analysis result."
                    );
                }


                displayEnvironmentalResult(
                    result.data,
                    result.interpretation
                );

                await displayEnvironmentalMap(hazard, requestData);

                console.log(
                    "Environmental analysis completed:",
                    result
                );

                return;
            }

            throw new Error(
                `Unknown job status: ${job.status || "missing status"}.`
            );
        }

        throw new Error(
            "Analysis exceeded 30 minutes. Check server logs."
        );

    } catch (error) {

        console.error(
            "Environmental analysis failed:",
            error
        );

        updateEnvironmentalMessage(
            `Analysis failed: ${error.message}`,
            true
        );

    } finally {

        environmentalAnalysisInProgress = false;

        button.disabled = false;

        button.textContent =
            "Run Environmental Analysis";
    }
}




// ==================================================
// Map Resize Handling
// ==================================================

window.addEventListener("resize", () => {

    if (map) {
        map.invalidateSize(true);
    }
});


// ==================================================
// Application Startup
// ==================================================

document.addEventListener("DOMContentLoaded", () => {

    initializeMap();

    setupLayerControls();

    setupLocationSearch();

    setupDateInputs();

    setupAnalysisControls();

    setupEnvironmentalControls();

    loadMetadata().catch(error => {
        console.error("Initial dashboard loading failed:", error);
    });

});