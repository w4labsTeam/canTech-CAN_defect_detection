
"use strict";

// =====================================================
// CONFIGURATION
// =====================================================

const MAX_CHART_POINTS = 60;

let inspectionChart = null;
let defectChart = null;

let inspectionHistory = [];
let defectHistory = [];

let eventSource = null;


// =====================================================
// DOM HELPERS
// =====================================================

function setText(id, value) {

    const element = document.getElementById(id);

    if (element) {
        element.textContent = value;
    }

}


function formatNumber(value) {

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "0";
    }

    return Math.round(number).toLocaleString();

}


function formatDecimal(value, decimals = 2) {

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return (0).toFixed(decimals);
    }

    return number.toFixed(decimals);

}


function formatTime(date = new Date()) {

    return date.toLocaleTimeString(
        undefined,
        {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        }
    );

}


// =====================================================
// CLOCK
// =====================================================

function updateClock() {

    setText(
        "clock",
        formatTime()
    );

}

setInterval(updateClock, 1000);

updateClock();


// =====================================================
// STATUS INDICATORS
// =====================================================

function updateStatusBadge(elementId, value) {

    const element = document.getElementById(elementId);

    if (!element) {
        return;
    }

    const status = String(value || "UNKNOWN").toUpperCase();

    element.textContent = status;

    element.className = "status-badge";

    if (
        ["CONNECTED", "RUNNING", "LOADED", "ONLINE"].includes(status)
    ) {

        element.classList.add("online");

    } else if (
        ["DISCONNECTED", "OFFLINE", "ERROR", "FAILED"].includes(status)
    ) {

        element.classList.add("offline");

    } else if (
        ["STARTING", "INITIALIZING", "RECONNECTING"].includes(status)
    ) {

        element.classList.add("warning");

    } else {

        element.classList.add("unknown");

    }

}


// =====================================================
// HEADER CONNECTION INDICATOR
// =====================================================

function updateConnectionIndicator(connected) {

    const dot = document.getElementById("mqtt-dot");
    const label = document.getElementById("mqtt-label");

    if (!dot || !label) {
        return;
    }

    if (connected) {

        dot.className = "status-dot connected";
        label.textContent = "DASHBOARD LIVE";

    } else {

        dot.className = "status-dot disconnected";
        label.textContent = "RECONNECTING";

    }

}


// =====================================================
// INITIALIZE CHARTS
// =====================================================

function initializeCharts() {

    if (typeof Chart === "undefined") {

        console.error(
            "Chart.js is unavailable. Check your internet connection."
        );

        return;

    }

    Chart.defaults.color = "#94a3b8";
    Chart.defaults.font.family = "'Segoe UI', Arial, sans-serif";

    // ---------------------------------------------
    // Inspection rate chart
    // ---------------------------------------------

    const inspectionContext = document
        .getElementById("inspection-chart")
        .getContext("2d");

    inspectionChart = new Chart(
        inspectionContext,
        {
            type: "line",

            data: {
                labels: [],

                datasets: [
                    {
                        label: "Inspection Rate",

                        data: [],

                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59, 130, 246, 0.10)",

                        borderWidth: 2,

                        fill: true,

                        tension: 0.35,

                        pointRadius: 2,
                        pointHoverRadius: 5,
                    }
                ]
            },

            options: {

                responsive: true,
                maintainAspectRatio: false,

                animation: false,

                interaction: {
                    intersect: false,
                    mode: "index",
                },

                plugins: {

                    legend: {
                        display: false,
                    },

                    tooltip: {
                        backgroundColor: "#172438",
                        borderColor: "#334155",
                        borderWidth: 1,
                        titleColor: "#f1f5f9",
                        bodyColor: "#cbd5e1",
                    }

                },

                scales: {

                    x: {
                        grid: {
                            color: "rgba(148, 163, 184, 0.08)",
                        },

                        ticks: {
                            maxTicksLimit: 6,
                        }
                    },

                    y: {
                        beginAtZero: true,

                        grid: {
                            color: "rgba(148, 163, 184, 0.10)",
                        },

                        title: {
                            display: true,
                            text: "CANs / minute",
                        }
                    }

                }

            }

        }
    );


    // ---------------------------------------------
    // Defect percentage chart
    // ---------------------------------------------

    const defectContext = document
        .getElementById("defect-chart")
        .getContext("2d");

    defectChart = new Chart(
        defectContext,
        {
            type: "line",

            data: {
                labels: [],

                datasets: [
                    {
                        label: "Defect Percentage",

                        data: [],

                        borderColor: "#ef4444",
                        backgroundColor: "rgba(239, 68, 68, 0.10)",

                        borderWidth: 2,

                        fill: true,

                        tension: 0.35,

                        pointRadius: 2,
                        pointHoverRadius: 5,
                    }
                ]
            },

            options: {

                responsive: true,
                maintainAspectRatio: false,

                animation: false,

                interaction: {
                    intersect: false,
                    mode: "index",
                },

                plugins: {

                    legend: {
                        display: false,
                    },

                    tooltip: {
                        backgroundColor: "#172438",
                        borderColor: "#334155",
                        borderWidth: 1,
                        titleColor: "#f1f5f9",
                        bodyColor: "#cbd5e1",
                        callbacks: {
                            label: (context) =>
                                `Defect rate: ${context.parsed.y.toFixed(2)}%`
                        }
                    }

                },

                scales: {

                    x: {
                        grid: {
                            color: "rgba(148, 163, 184, 0.08)",
                        },

                        ticks: {
                            maxTicksLimit: 6,
                        }
                    },

                    y: {
                        beginAtZero: true,

                        grid: {
                            color: "rgba(148, 163, 184, 0.10)",
                        },

                        title: {
                            display: true,
                            text: "Defect Percentage (%)",
                        }
                    }

                }

            }

        }
    );

}


// =====================================================
// UPDATE CHART DATA
// =====================================================

function updateCharts(statistics) {

    const now = formatTime();

    const rate = Number(statistics.inspection_rate) || 0;

    const defectPercentage =
        Number(statistics.defect_percentage) || 0;


    // Add latest samples.

    inspectionHistory.push({
        time: now,
        value: rate,
    });

    defectHistory.push({
        time: now,
        value: defectPercentage,
    });


    // Keep only the latest 60 samples.

    if (inspectionHistory.length > MAX_CHART_POINTS) {
        inspectionHistory.shift();
    }

    if (defectHistory.length > MAX_CHART_POINTS) {
        defectHistory.shift();
    }


    // Update inspection chart.

    if (inspectionChart) {

        inspectionChart.data.labels =
            inspectionHistory.map(item => item.time);

        inspectionChart.data.datasets[0].data =
            inspectionHistory.map(item => item.value);

        inspectionChart.update("none");

    }


    // Update defect chart.

    if (defectChart) {

        defectChart.data.labels =
            defectHistory.map(item => item.time);

        defectChart.data.datasets[0].data =
            defectHistory.map(item => item.value);

        defectChart.update("none");

    }

}


// =====================================================
// UPDATE PRODUCTION STATISTICS
// =====================================================

function updateStatistics(statistics) {

    // ---------------------------------------------
    // Lifetime statistics
    // ---------------------------------------------

    const total = Number(statistics.lifetime_total) || 0;

    const passed = Number(statistics.lifetime_passed) || 0;

    const defective =
        Number(statistics.lifetime_defective) || 0;


    // Lifetime yield.

    const yieldPercentage = total > 0
        ? (passed / total) * 100
        : 0;


    // Lifetime defect percentage.

    const lifetimeDefectPercentage = total > 0
        ? (defective / total) * 100
        : 0;


    setText(
        "total-inspected",
        formatNumber(total)
    );

    setText(
        "passed-cans",
        formatNumber(passed)
    );

    setText(
        "defective-cans",
        formatNumber(defective)
    );

    setText(
        "yield-percentage",
        formatDecimal(yieldPercentage)
    );

    setText(
        "lifetime-defect-percentage",
        formatDecimal(lifetimeDefectPercentage)
    );


    // ---------------------------------------------
    // Current session statistics
    // ---------------------------------------------

    const sessionTotal = Number(statistics.total) || 0;

    const sessionPassed = Number(statistics.passed) || 0;

    const sessionDefective =
        Number(statistics.defective) || 0;

    const sessionErrors = Number(statistics.errors) || 0;

    const sessionDefectPercentage =
        Number(statistics.defect_percentage) || 0;

    const inspectionRate =
        Number(statistics.inspection_rate) || 0;


    setText(
        "session-total",
        formatNumber(sessionTotal)
    );

    setText(
        "session-passed",
        formatNumber(sessionPassed)
    );

    setText(
        "session-defective",
        formatNumber(sessionDefective)
    );

    setText(
        "session-total-detail",
        formatNumber(sessionTotal)
    );

    setText(
        "session-passed-detail",
        formatNumber(sessionPassed)
    );

    setText(
        "session-defective-detail",
        formatNumber(sessionDefective)
    );

    setText(
        "session-errors-detail",
        formatNumber(sessionErrors)
    );

    setText(
        "session-defect-percentage",
        formatDecimal(sessionDefectPercentage)
    );

    setText(
        "inspection-rate",
        formatNumber(inspectionRate)
    );


    // Update charts.

    updateCharts(statistics);

}


// =====================================================
// UPDATE SYSTEM STATUS
// =====================================================

function updateSystemStatus(data) {

    const status = data.status || {};

    updateStatusBadge(
        "camera-status",
        status.camera
    );

    updateStatusBadge(
        "model-status",
        status.ai_model
    );

    updateStatusBadge(
        "service-status",
        status.inspection_service
    );

    updateStatusBadge(
        "mqtt-status",
        data.mqtt_connected
            ? "CONNECTED"
            : "DISCONNECTED"
    );

}


// =====================================================
// PROCESS DASHBOARD DATA
// =====================================================

function updateDashboard(data) {

    if (!data || typeof data !== "object") {
        return;
    }

    const statistics = data.statistics || {};

    updateConnectionIndicator(
        data.mqtt_connected === true
    );

    updateStatistics(statistics);

    updateSystemStatus(data);


    // ---------------------------------------------
    // Last update time
    // ---------------------------------------------

    const lastUpdate =
        data.last_statistics_received;

    if (lastUpdate) {

        const date = new Date(lastUpdate);

        if (!Number.isNaN(date.getTime())) {

            setText(
                "last-update",
                date.toLocaleTimeString()
            );

        }

    }

}


// =====================================================
// SERVER-SENT EVENTS
// =====================================================

function connectSSE() {

    console.log("[DASHBOARD] Connecting to Flask SSE...");

    eventSource = new EventSource("/events");


    eventSource.onopen = () => {

        console.log("[DASHBOARD] SSE connection established.");

        updateConnectionIndicator(true);

    };


    eventSource.onmessage = (event) => {

        try {

            const data = JSON.parse(event.data);

            updateDashboard(data);

        } catch (error) {

            console.error(
                "[DASHBOARD] Invalid SSE message:",
                error
            );

        }

    };


    eventSource.onerror = (error) => {

        console.error(
            "[DASHBOARD] SSE connection error:",
            error
        );

        updateConnectionIndicator(false);

        // EventSource automatically attempts to reconnect.

    };

}


// =====================================================
// APPLICATION INITIALIZATION
// =====================================================

document.addEventListener("DOMContentLoaded", () => {

    console.log("[DASHBOARD] Initializing dashboard...");

    initializeCharts();

    connectSSE();

});
