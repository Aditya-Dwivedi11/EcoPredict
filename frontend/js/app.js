
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

let map = null;
let rasterOverlay = null;
let currentLayer = null;
let rasterMetadata = null;
let rasterRequestId = 0;


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

    // Esri World Imagery satellite basemap
    L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
            attribution: "Tiles &copy; Esri",
            maxZoom: 19
        }
    ).addTo(map);

    // Initial study region: Kanpur
    map.setView([26.47, 80.32], 11);

    // Recalculate map dimensions after dashboard layout.
    requestAnimationFrame(() => {
        map.invalidateSize(true);
    });
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

async function loadMetadata() {

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

        rasterMetadata = await response.json();

        if (
            !rasterMetadata.layers ||
            !rasterMetadata.layers.before ||
            !rasterMetadata.layers.after ||
            !rasterMetadata.layers.difference
        ) {
            throw new Error("Invalid raster metadata structure.");
        }

        updateDashboardMetrics();
        updatePeriods();

        const bounds = getLayerBounds("before");

        // Wait for the browser to finish laying out the map.
        await new Promise(resolve => {
            requestAnimationFrame(() => {

                map.invalidateSize(true);

                map.fitBounds(bounds, {
                    padding: [5, 5],
                    maxZoom: 15,
                    animate: false
                });

                console.log(
                    "EcoPredict raster metadata:",
                    rasterMetadata
                );

                console.log(
                    "Raster bounds:",
                    bounds
                );

                console.log(
                    "Map bounds:",
                    map.getBounds().toBBoxString()
                );

                console.log(
                    "Map zoom:",
                    map.getZoom()
                );

                console.log(
                    "Map size:",
                    map.getSize()
                );

                resolve();
            });
        });

        // Load initial raster after map fitting.
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
        before.mean.toFixed(4);

    document.getElementById("after-ndvi").textContent =
        after.mean.toFixed(4);

    const change = after.mean - before.mean;

    const changeElement =
        document.getElementById("ndvi-change");

    changeElement.textContent =
        `${change > 0 ? "+" : ""}${change.toFixed(4)}`;

    changeElement.style.color =
        change < 0
            ? "#f16b70"
            : "#36c98f";

    document.getElementById("valid-pixels").textContent =
        difference.valid_pixel_count.toLocaleString();
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

            // Remove previous raster.
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
                changeRasterLayer(layer);
            }
        });
    });
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

    loadMetadata();
});
