
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

    if (analysisInProgress) {
        return;
    }

    const button =
        document.getElementById("run-analysis-button");

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

    button.textContent = "Running Satellite Analysis...";

    updateAnalysisMessage(
        "Connecting to Google Earth Engine. This may take several minutes."
    );

    updateStatus("Satellite analysis in progress...");

    console.log(
        "Submitting EcoPredict analysis request:",
        requestData
    );

    try {

        const response = await fetch(
            `${API_BASE}/api/v1/ndvi-analysis`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify(requestData)
            }
        );

        const result = await response.json();

        if (!response.ok) {

            const detail =
                typeof result.detail === "string"
                    ? result.detail
                    : JSON.stringify(result.detail);

            throw new Error(
                detail || `Analysis failed with HTTP ${response.status}`
            );
        }

        console.log(
            "Satellite analysis response:",
            result
        );

        updateAnalysisMessage(
            "Satellite analysis completed. Refreshing map and statistics..."
        );

        // Load the new metadata and raster outputs.
        await loadMetadata(true);

        updateAnalysisMessage(
            "Analysis completed successfully. NDVI maps and statistics have been updated."
        );

        updateStatus(
            "New satellite analysis completed successfully."
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

    loadMetadata().catch(error => {
        console.error("Initial dashboard loading failed:", error);
    });

});
