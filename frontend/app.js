/**
 * RSG Sales Intelligence AI Assistant — Frontend Client Application
 * Connects to the FastAPI backend, coordinates query lifecycle, renders interactive UI and charts.
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- DOM Element References ---
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");
  const queryForm = document.getElementById("queryForm");
  const queryInput = document.getElementById("queryInput");
  const charCounter = document.getElementById("charCounter");
  const submitBtn = document.getElementById("submitBtn");
  const btnSpinner = document.getElementById("btnSpinner");
  const btnText = document.getElementById("btnText");
  const emptyState = document.getElementById("emptyState");
  const resultsContainer = document.getElementById("resultsContainer");
  const chipButtons = document.querySelectorAll(".chip-btn");

  // --- Initial System Health Check ---
  async function checkSystemHealth() {
    try {
      const response = await fetch("/api/health");
      if (response.ok) {
        const data = await response.json();
        if (data.database_connected) {
          statusDot.classList.add("online");
          const engineLabel = data.gemini_configured ? "Gemini Ready" : "Deterministic Engine";
          statusText.textContent = `Online • ${data.valid_revenue_records} Valid Records • ${engineLabel}`;
        } else {
          statusText.textContent = "Database Disconnected";
        }
      } else {
        statusText.textContent = "Backend Degraded";
      }
    } catch {
      statusText.textContent = "Backend Offline";
    }
  }

  checkSystemHealth();

  // --- Formatters ---
  const formatINR = (val) => {
    if (val === null || val === undefined) return "N/A";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatNumber = (val) => {
    if (val === null || val === undefined) return "0";
    return new Intl.NumberFormat("en-IN").format(val);
  };

  // --- Input & Character Counter Listeners ---
  queryInput.addEventListener("input", () => {
    const len = queryInput.value.length;
    charCounter.textContent = `${len}/500`;
    if (len >= 480) {
      charCounter.style.color = "var(--color-warning)";
    } else {
      charCounter.style.color = "var(--text-muted)";
    }
  });

  // --- Clickable Prompt Chips ---
  chipButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        queryInput.value = prompt;
        queryInput.dispatchEvent(new Event("input"));
        submitQuery(prompt);
      }
    });
  });

  // --- Form Submission Handler ---
  queryForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) {
      showErrorAlert("Please enter a question before submitting.");
      return;
    }
    submitQuery(query);
  });

  // --- Query Dispatcher ---
  async function submitQuery(question) {
    setLoadingState(true);

    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question }),
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMsg = data.error || "An error occurred while processing your request.";
        showErrorAlert(errorMsg);
      } else {
        renderResults(data);
      }
    } catch (err) {
      showErrorAlert("Network error: Unable to reach the backend API. Please ensure the server is running.");
    } finally {
      setLoadingState(false);
    }
  }

  function setLoadingState(isLoading) {
    if (isLoading) {
      submitBtn.disabled = true;
      btnSpinner.style.display = "inline-block";
      btnText.textContent = "Analyzing...";
      resultsContainer.setAttribute("aria-busy", "true");
    } else {
      submitBtn.disabled = false;
      btnSpinner.style.display = "none";
      btnText.textContent = "Ask Assistant";
      resultsContainer.setAttribute("aria-busy", "false");
    }
  }

  function showErrorAlert(message) {
    emptyState.style.display = "none";
    resultsContainer.innerHTML = `
      <div class="error-box" role="alert">
        <span style="font-size: 1.25rem;">⚠️</span>
        <div>
          <strong>Error Processing Query:</strong>
          <p style="margin-top: 0.25rem;">${escapeHtml(message)}</p>
        </div>
      </div>
    `;
  }

  // --- Result Rendering Orchestrator ---
  function renderResults(data) {
    emptyState.style.display = "none";

    const isGemini = data.engine === "gemini";
    const engineBadgeHtml = isGemini
      ? `<span class="badge badge-engine-gemini" title="Intent parsed via Gemini 2.5 Flash">✨ Engine: Gemini AI</span>`
      : `<span class="badge badge-engine-fallback" title="Intent matched via verified deterministic fallback rules">🛡️ Engine: Deterministic Fallback</span>`;

    const latencyText = data.execution_trace?.latency_ms
      ? `${data.execution_trace.latency_ms} ms`
      : "instant";

    let supportingContentHtml = "";
    const intent = data.intent;
    const sup = data.supporting_data || {};

    // Render Intent-Specific Supporting Visuals
    if (intent === "TOTAL_REVENUE") {
      supportingContentHtml = renderTotalRevenueSupporting(sup);
    } else if (intent === "TOP_PRODUCT") {
      supportingContentHtml = renderTopProductSupporting(sup);
    } else if (intent === "MONTHLY_TREND") {
      supportingContentHtml = renderMonthlyTrendSupporting(sup);
    } else if (intent === "TOP_REGION") {
      supportingContentHtml = renderTopRegionSupporting(sup);
    } else if (intent === "REVENUE_DELTA") {
      supportingContentHtml = renderRevenueDeltaSupporting(sup);
    }

    const cardHtml = `
      <article class="result-card" aria-live="polite">
        <div class="result-header">
          <div class="badges-group">
            <span class="badge badge-intent">🎯 Intent: ${escapeHtml(data.intent)}</span>
            ${engineBadgeHtml}
          </div>
          <span class="latency-pill" title="Server calculation latency">⚡ Latency: ${latencyText}</span>
        </div>

        <div class="answer-box">
          <p class="answer-text">${escapeHtml(data.answer)}</p>
        </div>

        ${supportingContentHtml}

        <details class="trace-details">
          <summary class="trace-summary">
            <span>🔍 View Technical Audit & Trace</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">(Tool & Safety Verification)</span>
          </summary>
          <pre class="trace-content">${escapeHtml(JSON.stringify(data.execution_trace, null, 2))}</pre>
        </details>
      </article>
    `;

    resultsContainer.innerHTML = cardHtml;
  }

  // --- Sub-View Renderers ---

  function renderTotalRevenueSupporting(sup) {
    const net = sup.total_net_revenue || 0;
    const gross = sup.total_gross_revenue || 0;
    const disc = sup.total_discount_amount || 0;
    const units = sup.total_units_sold || 0;
    const txns = sup.valid_transaction_count || 0;

    const categories = sup.category_breakdown || [];
    const channels = sup.channel_breakdown || [];

    const catRows = categories.map((c) => `
      <tr>
        <td><strong>${escapeHtml(c.category)}</strong></td>
        <td>${formatINR(c.net_revenue)}</td>
        <td>${formatNumber(c.units_sold)}</td>
        <td>${c.transaction_count}</td>
      </tr>
    `).join("");

    const chanRows = channels.map((c) => `
      <tr>
        <td><strong>${escapeHtml(c.sales_channel)}</strong></td>
        <td>${formatINR(c.net_revenue)}</td>
        <td>${formatNumber(c.units_sold)}</td>
        <td>${c.transaction_count}</td>
      </tr>
    `).join("");

    return `
      <div class="kpi-grid">
        <div class="kpi-card">
          <span class="kpi-label">Total Net Revenue</span>
          <span class="kpi-value success">${formatINR(net)}</span>
          <span class="kpi-subtext">Earned after ₹${formatNumber(disc)} discounts</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Gross Transaction Value</span>
          <span class="kpi-value">${formatINR(gross)}</span>
          <span class="kpi-subtext">Sum of quantity × unit price</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Total Volume Sold</span>
          <span class="kpi-value">${formatNumber(units)} units</span>
          <span class="kpi-subtext">Across ${txns} valid orders</span>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem;">
        <div class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr><th>Category</th><th>Net Revenue</th><th>Units</th><th>Orders</th></tr>
            </thead>
            <tbody>${catRows}</tbody>
          </table>
        </div>

        <div class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr><th>Sales Channel</th><th>Net Revenue</th><th>Units</th><th>Orders</th></tr>
            </thead>
            <tbody>${chanRows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderTopProductSupporting(sup) {
    const products = sup.ranking || [];
    const rows = products.map((p, idx) => {
      const isGold = idx === 0 ? "gold" : "";
      return `
        <tr>
          <td><span class="rank-badge ${isGold}">#${idx + 1}</span></td>
          <td><strong>${escapeHtml(p.product)}</strong></td>
          <td><span class="scope-pill">${escapeHtml(p.category)}</span></td>
          <td style="font-weight: 600; color: ${idx === 0 ? "var(--color-success)" : "var(--text-primary)"}">
            ${formatINR(p.net_revenue)}
          </td>
          <td>${formatNumber(p.units_sold)}</td>
          <td>${p.transaction_count}</td>
        </tr>
      `;
    }).join("");

    return `
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr><th>Rank</th><th>Product</th><th>Category</th><th>Net Revenue</th><th>Units Sold</th><th>Orders</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderMonthlyTrendSupporting(sup) {
    const trend = sup.trend || [];
    const peak = sup.peak_month || {};
    const lowest = sup.lowest_month || {};
    const avg = sup.average_monthly_revenue || 0;

    const rows = trend.map((m) => {
      const isPeak = m.month === peak.month;
      const momText = m.mom_change_amount !== null
        ? `${m.mom_change_amount >= 0 ? "+" : ""}${formatINR(m.mom_change_amount)} (${m.mom_change_percent >= 0 ? "+" : ""}${m.mom_change_percent}%)`
        : "— (Baseline)";
      const momColor = (m.mom_change_amount || 0) >= 0 ? "var(--color-success)" : "#f87171";

      return `
        <tr>
          <td>
            <strong>${escapeHtml(m.month)}</strong>
            ${isPeak ? '<span class="badge badge-intent" style="margin-left: 0.4rem; font-size: 0.65rem;">Peak</span>' : ""}
          </td>
          <td style="font-weight: 600;">${formatINR(m.net_revenue)}</td>
          <td>${formatNumber(m.units_sold)}</td>
          <td>${m.transaction_count}</td>
          <td style="color: ${m.mom_change_amount !== null ? momColor : "var(--text-muted)"}; font-weight: 500;">
            ${momText}
          </td>
        </tr>
      `;
    }).join("");

    const chartSvg = generateMonthlyBarChartSvg(trend);

    return `
      <div class="kpi-grid">
        <div class="kpi-card">
          <span class="kpi-label">Peak Revenue Month</span>
          <span class="kpi-value success">${escapeHtml(peak.month || "N/A")}</span>
          <span class="kpi-subtext">${formatINR(peak.net_revenue)}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Lowest Revenue Month</span>
          <span class="kpi-value">${escapeHtml(lowest.month || "N/A")}</span>
          <span class="kpi-subtext">${formatINR(lowest.net_revenue)}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Average Monthly Revenue</span>
          <span class="kpi-value">${formatINR(avg)}</span>
          <span class="kpi-subtext">Across ${trend.length} calendar months</span>
        </div>
      </div>

      <div class="chart-container">
        <span class="chart-title">Monthly Net Revenue Trend (H1 2026)</span>
        ${chartSvg}
      </div>

      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr><th>Month</th><th>Net Revenue</th><th>Units</th><th>Orders</th><th>MoM Growth</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderTopRegionSupporting(sup) {
    const regions = sup.ranking_by_revenue || [];
    const rows = regions.map((r, idx) => {
      const isGold = idx === 0 ? "gold" : "";
      return `
        <tr>
          <td><span class="rank-badge ${isGold}">#${idx + 1}</span></td>
          <td><strong>${escapeHtml(r.region)}</strong></td>
          <td style="font-weight: 600; color: ${idx === 0 ? "var(--color-success)" : "var(--text-primary)"}">
            ${formatINR(r.net_revenue)}
          </td>
          <td>${r.revenue_share_percent}%</td>
          <td>${formatNumber(r.units_sold)}</td>
          <td>${r.units_share_percent}%</td>
          <td>${r.transaction_count}</td>
        </tr>
      `;
    }).join("");

    return `
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr><th>Rank</th><th>Region</th><th>Net Revenue</th><th>Revenue Share</th><th>Units Sold</th><th>Volume Share</th><th>Orders</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderRevenueDeltaSupporting(sup) {
    const baseMonth = sup.base_month || "";
    const baseRev = sup.base_revenue || 0;
    const targetMonth = sup.target_month || "";
    const targetRev = sup.target_revenue || 0;
    const absChange = sup.absolute_change || 0;
    const pctChange = sup.percentage_change || 0;
    const isPositive = absChange >= 0;

    return `
      <div class="kpi-grid">
        <div class="kpi-card">
          <span class="kpi-label">Baseline Month (${escapeHtml(baseMonth)})</span>
          <span class="kpi-value">${formatINR(baseRev)}</span>
          <span class="kpi-subtext">Starting reference point</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Target Month (${escapeHtml(targetMonth)})</span>
          <span class="kpi-value">${formatINR(targetRev)}</span>
          <span class="kpi-subtext">Comparison period</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Net Delta (Change)</span>
          <span class="kpi-value ${isPositive ? "success" : "warning"}">
            ${isPositive ? "+" : ""}${formatINR(absChange)}
          </span>
          <span class="kpi-subtext" style="font-weight: 600; color: ${isPositive ? "var(--color-success)" : "#f87171"};">
            ${isPositive ? "▲" : "▼"} ${isPositive ? "+" : ""}${pctChange}% change
          </span>
        </div>
      </div>
    `;
  }

  // --- Pure SVG Responsive Bar Chart Generator ---
  function generateMonthlyBarChartSvg(trendData) {
    if (!trendData || trendData.length === 0) return "";

    const svgWidth = 700;
    const svgHeight = 220;
    const padding = { top: 35, right: 20, bottom: 35, left: 20 };
    const chartWidth = svgWidth - padding.left - padding.right;
    const chartHeight = svgHeight - padding.top - padding.bottom;

    const maxRev = Math.max(...trendData.map((d) => d.net_revenue), 1);
    const barWidth = Math.min(chartWidth / trendData.length - 20, 60);

    const bars = trendData.map((d, idx) => {
      const step = chartWidth / trendData.length;
      const x = padding.left + idx * step + (step - barWidth) / 2;
      const barHeight = (d.net_revenue / maxRev) * chartHeight;
      const y = padding.top + chartHeight - barHeight;
      const label = d.month.replace("2026-", "M");
      const formattedVal = `₹${Math.round(d.net_revenue / 1000)}k`;

      return `
        <g class="chart-bar-group">
          <!-- Value Label -->
          <text x="${x + barWidth / 2}" y="${y - 8}" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="sans-serif">${formattedVal}</text>
          <!-- Bar -->
          <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="url(#barGradient)" />
          <!-- Month Label -->
          <text x="${x + barWidth / 2}" y="${svgHeight - 12}" text-anchor="middle" fill="#cbd5e1" font-size="12" font-weight="600" font-family="sans-serif">${label}</text>
        </g>
      `;
    }).join("");

    return `
      <svg class="chart-svg" viewBox="0 0 ${svgWidth} ${svgHeight}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monthly Revenue Bar Chart">
        <defs>
          <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#3b82f6" />
            <stop offset="100%" stop-color="#1d4ed8" />
          </linearGradient>
        </defs>
        <!-- Baseline axis -->
        <line x1="${padding.left}" y1="${padding.top + chartHeight}" x2="${svgWidth - padding.right}" y2="${padding.top + chartHeight}" stroke="#334155" stroke-width="1" />
        ${bars}
      </svg>
    `;
  }

  // --- Utility ---
  function escapeHtml(str) {
    if (typeof str !== "string") return str;
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
