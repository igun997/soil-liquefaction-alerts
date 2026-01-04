/**
 * Liquefaction Alert Detection System - Client-side JavaScript
 */

// API endpoints
const API = {
    analyze: {
        quick: '/api/analyze/quick',
        full: '/api/analyze/full',
    },
    data: {
        earthquakes: '/api/earthquakes',
        weather: '/api/weather',
        elevation: '/api/elevation',
        terrain: '/api/terrain',
        landcover: '/api/landcover',
        siteData: '/api/site-data',
    },
};

/**
 * Fetch site data for a location
 */
async function fetchSiteData(lat, lon) {
    try {
        const response = await fetch(
            `${API.data.siteData}?lat=${lat}&lon=${lon}`
        );
        if (!response.ok) throw new Error('Failed to fetch site data');
        return await response.json();
    } catch (error) {
        console.error('Error fetching site data:', error);
        return null;
    }
}

/**
 * Run quick liquefaction analysis
 */
async function runQuickAnalysis(params) {
    try {
        const response = await fetch(API.analyze.quick, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(params),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Analysis failed');
        }

        return await response.json();
    } catch (error) {
        console.error('Analysis error:', error);
        throw error;
    }
}

/**
 * Run full liquefaction analysis with detailed soil profile
 */
async function runFullAnalysis(params) {
    try {
        const response = await fetch(API.analyze.full, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(params),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Analysis failed');
        }

        return await response.json();
    } catch (error) {
        console.error('Analysis error:', error);
        throw error;
    }
}

/**
 * Get risk color based on factor of safety
 */
function getRiskColor(fs) {
    if (fs < 0.5) return '#dc3545';  // Very High - Red
    if (fs < 1.0) return '#fd7e14';  // High - Orange
    if (fs < 1.5) return '#ffc107';  // Moderate - Yellow
    return '#28a745';                 // Low - Green
}

/**
 * Get risk level text
 */
function getRiskLevel(fs) {
    if (fs < 0.5) return 'Very High';
    if (fs < 1.0) return 'High';
    if (fs < 1.5) return 'Moderate';
    return 'Low';
}

/**
 * Format number with specified decimals
 */
function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined) return '--';
    return Number(value).toFixed(decimals);
}

/**
 * Create depth profile chart data
 */
function createProfileChartData(layerResults) {
    return layerResults.map(layer => ({
        depth: layer.depth,
        fs: layer.factor_of_safety,
        csr: layer.csr,
        crr: layer.crr,
        risk: layer.risk_level,
    }));
}

/**
 * Export results to JSON
 */
function exportResults(result) {
    const dataStr = JSON.stringify(result, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `liquefaction-analysis-${result.request_id}.json`;
    a.click();

    URL.revokeObjectURL(url);
}

/**
 * Generate analysis report HTML
 */
function generateReport(result) {
    const risk = result.risk_assessment;
    const eq = result.earthquake;

    return `
        <html>
        <head>
            <title>Liquefaction Analysis Report</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 2rem; }
                h1 { color: #1a5276; }
                .section { margin: 1.5rem 0; }
                .risk-box { padding: 1rem; border-radius: 8px; }
                .risk-very-high { background: #f8d7da; }
                .risk-high { background: #fff3cd; }
                .risk-moderate { background: #fff9e6; }
                .risk-low { background: #d4edda; }
                table { width: 100%; border-collapse: collapse; }
                th, td { border: 1px solid #ddd; padding: 0.5rem; }
                th { background: #f8f9fa; }
            </style>
        </head>
        <body>
            <h1>Liquefaction Analysis Report</h1>
            <p>Generated: ${new Date().toLocaleString()}</p>
            <p>Analysis ID: ${result.request_id}</p>

            <div class="section">
                <h2>Location</h2>
                <p>Coordinates: ${result.location.latitude}, ${result.location.longitude}</p>
                ${result.location.elevation ? `<p>Elevation: ${result.location.elevation} m</p>` : ''}
            </div>

            <div class="section">
                <h2>Risk Assessment</h2>
                <div class="risk-box risk-${risk.overall_risk}">
                    <h3>Factor of Safety: ${risk.overall_fs.toFixed(2)}</h3>
                    <p>Risk Level: ${risk.overall_risk.toUpperCase()}</p>
                    <p>Critical Depth: ${risk.critical_depth} m</p>
                    ${risk.lpi ? `<p>LPI: ${risk.lpi.toFixed(1)}</p>` : ''}
                </div>
            </div>

            <div class="section">
                <h2>Earthquake Data</h2>
                <p>Magnitude: M${eq.magnitude}</p>
                <p>PGA at Site: ${eq.pga.toFixed(3)} g</p>
                ${eq.location ? `<p>Location: ${eq.location}</p>` : ''}
            </div>

            <div class="section">
                <h2>Recommendation</h2>
                <p>${risk.recommendation}</p>
            </div>

            <div class="section">
                <h2>Layer Results</h2>
                <table>
                    <tr>
                        <th>Depth (m)</th>
                        <th>CSR</th>
                        <th>CRR</th>
                        <th>FS</th>
                        <th>Risk</th>
                    </tr>
                    ${result.layer_results.map(layer => `
                        <tr>
                            <td>${layer.depth}</td>
                            <td>${layer.csr.toFixed(3)}</td>
                            <td>${layer.crr.toFixed(3)}</td>
                            <td>${layer.factor_of_safety.toFixed(2)}</td>
                            <td>${layer.risk_level}</td>
                        </tr>
                    `).join('')}
                </table>
            </div>

            <footer style="margin-top: 2rem; color: #666; font-size: 0.9rem;">
                <p>Methodology: Boulanger & Idriss (2014)</p>
                <p>Generated by Liquefaction Alert Detection System</p>
            </footer>
        </body>
        </html>
    `;
}

// Export functions for use in HTML
window.LiquefactionApp = {
    API,
    fetchSiteData,
    runQuickAnalysis,
    runFullAnalysis,
    getRiskColor,
    getRiskLevel,
    formatNumber,
    createProfileChartData,
    exportResults,
    generateReport,
};
