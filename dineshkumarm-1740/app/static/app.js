/* VoltSurge static frontend (no build step).
   Flow:
   1) POST /api/dataset/upload (multipart) -> preview + columns
   2) POST /api/dataset/select (json) -> processed stored in session
   3) GET /api/metrics/summary, /api/anomalies, /api/timeseries (optional region filter)
*/

// PUBLIC_INTERFACE
function formatNumber(n, digits = 2) {
  /** Format numbers for KPI display. */
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(n);
}

function $(id) {
  return document.getElementById(id);
}

function setHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle("hidden", !!hidden);
}

function setDisabled(el, disabled) {
  if (!el) return;
  el.disabled = !!disabled;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const API_BASE = ""; // same-origin deployment; keep empty. (All API paths already start with /api)

function normalizeApiPath(path) {
  // Allow callers to pass "/api/..." or "api/..." or full URLs; normalize for consistency.
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (path.startsWith("/")) return `${API_BASE}${path}`;
  return `${API_BASE}/${path}`;
}

function describeFetchFailure(err) {
  const msg = String(err?.message || err || "");
  // Browser typically throws TypeError: Failed to fetch for network/CORS/mixed content issues.
  if (msg.toLowerCase().includes("failed to fetch")) {
    return "Network error: failed to reach backend. If you're running the API on a different origin, ensure CORS is enabled and the server is running.";
  }
  return `Network error: ${msg || "Unknown error"}`;
}

async function fetchJson(path, opts = {}) {
  const url = normalizeApiPath(path);

  try {
    const res = await fetch(url, {
      credentials: "include",
      ...opts,
    });

    const text = await res.text();
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = { raw: text };
    }

    return { ok: res.ok, status: res.status, json };
  } catch (err) {
    // Network/CORS issues never return a response; represent them consistently.
    return { ok: false, status: 0, json: { detail: describeFetchFailure(err) } };
  }
}

async function postJson(path, body) {
  return fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

async function postFormData(path, formData) {
  return fetchJson(path, { method: "POST", body: formData });
}

function showToast(message, kind = "info") {
  const toast = $("toast");
  if (!toast) return;

  toast.className = `toast ${kind === "error" ? "toastError" : kind === "success" ? "toastSuccess" : "toastInfo"}`;
  toast.textContent = message;
  setHidden(toast, false);

  window.clearTimeout(showToast._t);
  showToast._t = window.setTimeout(() => setHidden(toast, true), 3400);
}
showToast._t = 0;

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function isNonEmptyString(s) {
  return typeof s === "string" && s.trim() !== "";
}

function guessColumn(columns, candidates) {
  const lower = new Map(columns.map((c) => [String(c).toLowerCase(), c]));
  for (const cand of candidates) {
    const k = cand.toLowerCase();
    if (lower.has(k)) return lower.get(k);
  }
  // partial contains
  for (const c of columns) {
    const lc = String(c).toLowerCase();
    for (const cand of candidates) {
      if (lc.includes(cand.toLowerCase())) return c;
    }
  }
  return "";
}

function buildOptions(selectEl, options, { includeBlank = false, blankLabel = "None", selected = "" } = {}) {
  if (!selectEl) return;
  selectEl.innerHTML = "";

  if (includeBlank) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = blankLabel;
    selectEl.appendChild(opt);
  }

  for (const o of options) {
    const opt = document.createElement("option");
    opt.value = String(o);
    opt.textContent = String(o);
    if (String(o) === String(selected)) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function renderPreviewTable(columns, rows) {
  const thead = $("previewThead");
  const tbody = $("previewTbody");
  if (!thead || !tbody) return;

  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!Array.isArray(columns) || columns.length === 0) return;

  const trh = document.createElement("tr");
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c;
    trh.appendChild(th);
  }
  thead.appendChild(trh);

  for (const r of rows || []) {
    const tr = document.createElement("tr");
    for (const c of columns) {
      const td = document.createElement("td");
      const v = r ? r[c] : "";
      td.textContent = v === null || v === undefined ? "" : String(v);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function renderWarnings(warnings) {
  const wrap = $("uploadWarnings");
  if (!wrap) return;

  if (!Array.isArray(warnings) || warnings.length === 0) {
    setHidden(wrap, true);
    wrap.innerHTML = "";
    return;
  }

  wrap.innerHTML = `
    <div class="warningsHead">Warnings</div>
    <ul>
      ${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}
    </ul>
  `;
  setHidden(wrap, false);
}

function renderMetaGrid(el, items) {
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = "";
    setHidden(el, true);
    return;
  }
  el.innerHTML = items
    .map(
      ({ label, value }) => `
      <div class="metaItem">
        <div class="metaLabel">${escapeHtml(label)}</div>
        <div class="metaValue">${escapeHtml(value)}</div>
      </div>
    `
    )
    .join("");
  setHidden(el, false);
}

function uniq(values) {
  const out = [];
  const seen = new Set();
  for (const v of values || []) {
    const s = String(v ?? "");
    if (seen.has(s)) continue;
    seen.add(s);
    out.push(v);
  }
  return out;
}

function extractRegionsFromProcessedPreview(previewRows) {
  // We get preview rows from /api/dataset/select response. These include `region` if region_column was set.
  const regions = [];
  for (const r of previewRows || []) {
    const val = r?.region;
    if (isNonEmptyString(val)) regions.push(val);
  }
  return uniq(regions).sort((a, b) => String(a).localeCompare(String(b)));
}

let chart = null;

function ensureChart() {
  const canvas = $("usageChart");
  if (!canvas) return null;
  if (chart) return chart;

  const ctx = canvas.getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "kWh",
          data: [],
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.10)",
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.2,
          fill: true,
        },
        {
          label: "Anomalies",
          data: [],
          showLine: false,
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed?.y;
              if (v === null || v === undefined || Number.isNaN(v)) return `${ctx.dataset.label}: —`;
              return `${ctx.dataset.label}: ${formatNumber(v, 3)} kWh`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 8,
            callback: function (value) {
              // labels are ISO strings
              const label = this.getLabelForValue(value);
              // show YYYY-MM-DD if present
              if (typeof label === "string" && label.length >= 10) return label.slice(0, 10);
              return label;
            },
          },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            callback: (v) => `${v}`,
          },
        },
      },
    },
  });

  return chart;
}

function updateChartFromTimeseries(timeseries) {
  const c = ensureChart();
  if (!c) return;

  const labels = timeseries?.labels || [];
  const datasets = timeseries?.datasets || [];

  // Expect datasets[0] = kWh, datasets[1] = anomaly series (possibly absent)
  const kwhDs = datasets[0] || { label: "kWh", data: [] };
  const anomDs = datasets[1] || { label: "Anomalies", data: [] };

  c.data.labels = labels;
  c.data.datasets[0].label = kwhDs.label || "kWh";
  c.data.datasets[0].data = Array.isArray(kwhDs.data) ? kwhDs.data : [];

  // Anomalies rendered as points only: we use anomaly series where non-anomaly points are null.
  c.data.datasets[1].label = anomDs.label || "Anomalies";
  c.data.datasets[1].data = Array.isArray(anomDs.data) ? anomDs.data : [];

  c.update();
}

function renderAlerts(anomalyResp) {
  const ul = $("alertsList");
  const empty = $("alertsEmpty");
  const metaSmall = $("metaSmall");
  if (!ul || !empty || !metaSmall) return;

  const anomalies = anomalyResp?.anomalies || [];
  const baseline = anomalyResp?.baseline_avg_kwh ?? 0;
  const region = anomalyResp?.region ?? "";

  ul.innerHTML = "";

  if (!Array.isArray(anomalies) || anomalies.length === 0) {
    setHidden(empty, false);
  } else {
    setHidden(empty, true);
    for (const a of anomalies) {
      const li = document.createElement("li");
      li.className = "alertItem";
      const dt = String(a.date_iso || "");
      const pct = a.percent_above_average ?? 0;
      const kwh = a.kwh ?? null;
      const reg = a.region ?? "";
      li.innerHTML = `
        <div class="alertMain">
          <div class="alertTitle">
            <span class="pill pillDanger">Anomaly</span>
            <span class="alertDate">${escapeHtml(dt.slice(0, 19).replace("T", " "))}</span>
          </div>
          <div class="alertValue">
            <span class="strong">${escapeHtml(formatNumber(kwh, 3))} kWh</span>
            <span class="mutedSmall">(${escapeHtml(formatNumber(pct, 1))}% above avg)</span>
          </div>
        </div>
        <div class="alertMeta">
          <span class="mutedSmall">Baseline avg: ${escapeHtml(formatNumber(baseline, 3))} kWh</span>
          ${
            isNonEmptyString(reg)
              ? `<span class="dotSep">•</span><span class="mutedSmall">Region: ${escapeHtml(reg)}</span>`
              : ""
          }
        </div>
      `;
      ul.appendChild(li);
    }
  }

  metaSmall.innerHTML = `
    <div class="metaSmallRow"><span class="mutedSmall">Filter:</span> <span class="monoSmall">${
      isNonEmptyString(region) ? escapeHtml(region) : "All regions"
    }</span></div>
    <div class="metaSmallRow"><span class="mutedSmall">Baseline avg:</span> <span class="monoSmall">${escapeHtml(
      formatNumber(baseline, 3)
    )} kWh</span></div>
    <div class="metaSmallRow"><span class="mutedSmall">Anomalies:</span> <span class="monoSmall">${escapeHtml(
      String(anomalyResp?.anomaly_count ?? anomalies.length ?? 0)
    )}</span></div>
  `;
  setHidden(metaSmall, false);
}

function setKpis(summaryResp, anomalyResp) {
  $("kpiAvg").textContent = formatNumber(summaryResp?.average_kwh, 3);
  $("kpiMax").textContent = formatNumber(summaryResp?.max_kwh, 3);
  $("kpiTotal").textContent = formatNumber(summaryResp?.total_kwh, 3);
  $("kpiAnoms").textContent = String(anomalyResp?.anomaly_count ?? "—");
}

function getRegionFilterValue() {
  const sel = $("regionFilter");
  if (!sel) return "";
  return sel.value || "";
}

function setConnectivityBadge(ok) {
  const el = $("connBadge");
  if (!el) return;
  if (ok) {
    el.textContent = "Connected";
    el.className = "badge badgeOk";
  } else {
    el.textContent = "Offline";
    el.className = "badge badgeBad";
  }
}

async function refreshDebug() {
  const sessionPre = $("sessionPre");
  const statusPre = $("statusPre");
  if (!sessionPre || !statusPre) return;

  const session = await fetchJson("/api/session");
  const status = await fetchJson("/api/dataset/status");

  sessionPre.textContent = pretty(session.json);
  statusPre.textContent = pretty(status.json);
}

function isMissingProcessedDatasetError(resp) {
  // Backend uses 400 with this message when processed dataset hasn't been created yet.
  const detail = String(resp?.json?.detail || "");
  return resp?.status === 400 && detail.toLowerCase().includes("no processed dataset found");
}

async function loadDashboard() {
  const refreshBtn = $("refreshBtn");
  setDisabled(refreshBtn, true);

  const region = getRegionFilterValue();
  const qs = region ? `?region=${encodeURIComponent(region)}` : "";

  const [summary, anomalies, timeseries] = await Promise.all([
    fetchJson(`/api/metrics/summary${qs}`),
    fetchJson(`/api/anomalies${qs}`),
    fetchJson(`/api/timeseries${qs}`),
  ]);

  // Common case: user hasn't processed selection yet.
  if (isMissingProcessedDatasetError(summary) || isMissingProcessedDatasetError(anomalies) || isMissingProcessedDatasetError(timeseries)) {
    showToast("No processed dataset yet. Upload a CSV and run Step 2 (Configure) first.", "error");
    setDisabled(refreshBtn, false);
    return;
  }

  if (!summary.ok) {
    showToast(summary.json?.detail || "Failed to load summary metrics.", "error");
    setDisabled(refreshBtn, false);
    return;
  }
  if (!anomalies.ok) {
    showToast(anomalies.json?.detail || "Failed to load anomalies.", "error");
    setDisabled(refreshBtn, false);
    return;
  }
  if (!timeseries.ok) {
    showToast(timeseries.json?.detail || "Failed to load timeseries.", "error");
    setDisabled(refreshBtn, false);
    return;
  }

  setKpis(summary.json, anomalies.json);
  renderAlerts(anomalies.json);
  updateChartFromTimeseries(timeseries.json);

  setDisabled(refreshBtn, false);
}

function makeDemoCsvBlob() {
  // Tiny dataset with anomalies and regions; designed to work with the app's default parsers.
  const lines = [
    "date,usage,region",
    "2024-01-01,10,North",
    "2024-01-02,12,North",
    "2024-01-03,11,North",
    "2024-01-04,30,North",
    "2024-01-05,10,North",
    "2024-01-01,8,South",
    "2024-01-02,9,South",
    "2024-01-03,8.5,South",
    "2024-01-04,20,South",
    "2024-01-05,9,South",
    "2024-01-05,9,South", // duplicate row to show de-dupe
    "2024-01-06,,South", // missing usage to show missing handling
  ];
  return new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
}

async function handleUpload(file) {
  if (!file) {
    showToast("Choose a CSV file first.", "error");
    return null;
  }

  const uploadBtn = $("uploadBtn");
  setDisabled(uploadBtn, true);

  const fd = new FormData();
  fd.append("file", file, file.name || "upload.csv");

  const res = await postFormData("/api/dataset/upload", fd);
  setDisabled(uploadBtn, false);

  if (!res.ok) {
    showToast(res.json?.detail || "Upload failed.", "error");
    return null;
  }

  const data = res.json;

  renderMetaGrid($("uploadMeta"), [
    { label: "File", value: data.filename },
    { label: "Rows (parsed)", value: String(data.row_count) },
    { label: "Rows (after cleaning)", value: String(data.row_count_after_cleaning) },
    { label: "Duplicates removed", value: String(data.duplicate_rows_removed) },
  ]);

  renderPreviewTable(data.columns, data.preview_rows);
  renderWarnings(data.warnings);

  // Enable config step.
  const columns = Array.isArray(data.columns) ? data.columns : [];
  buildOptions($("dateColumn"), columns, {
    selected: guessColumn(columns, ["date", "datetime", "timestamp", "time"]),
  });
  buildOptions($("usageColumn"), columns, {
    selected: guessColumn(columns, ["usage", "kwh", "kw", "watts", "watt", "energy", "consumption"]),
  });

  // Region optional select: include blank
  buildOptions($("regionColumn"), columns, {
    includeBlank: true,
    blankLabel: "None",
    selected: guessColumn(columns, ["region", "area", "site", "location"]),
  });

  setDisabled($("dateColumn"), false);
  setDisabled($("usageColumn"), false);
  setDisabled($("usageUnit"), false);
  setDisabled($("regionColumn"), false);
  setDisabled($("processBtn"), false);
  $("configHint").textContent = "Select columns and process to view dashboard";

  showToast("Upload complete. Configure columns below.", "success");

  return data;
}

async function handleProcessSelection() {
  const dateColumn = $("dateColumn").value;
  const usageColumn = $("usageColumn").value;
  const usageUnit = $("usageUnit").value;
  const regionColumn = $("regionColumn").value || null;

  if (!isNonEmptyString(dateColumn) || !isNonEmptyString(usageColumn) || !isNonEmptyString(usageUnit)) {
    showToast("Select date column, usage column, and unit.", "error");
    return null;
  }

  const processBtn = $("processBtn");
  setDisabled(processBtn, true);

  const res = await postJson("/api/dataset/select", {
    date_column: dateColumn,
    usage_column: usageColumn,
    usage_unit: usageUnit,
    region_column: regionColumn,
  });

  setDisabled(processBtn, false);

  if (!res.ok) {
    showToast(res.json?.detail || "Processing failed.", "error");
    return null;
  }

  const data = res.json;

  renderMetaGrid($("processMeta"), [
    { label: "Rows stored", value: String(data.summary?.row_count ?? "—") },
    { label: "Dropped rows", value: String(data.summary?.dropped_rows ?? "—") },
    { label: "Null kWh rows", value: String(data.summary?.included_null_rows ?? "—") },
    { label: "Unit normalized", value: "kWh" },
  ]);

  // Enable dashboard controls.
  const regions = extractRegionsFromProcessedPreview(data.preview_rows);
  const regionFilter = $("regionFilter");
  if (regionFilter) {
    const hasRegions = regions.length > 0;
    const opts = hasRegions ? regions : [];
    // Keep "All" option already in HTML and then add regions
    regionFilter.innerHTML = `<option value="">All</option>` + opts.map((r) => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join("");
    setDisabled(regionFilter, !hasRegions);
  }
  setDisabled($("refreshBtn"), false);

  showToast("Processed. Loading dashboard…", "success");
  await loadDashboard();

  return data;
}

function resetUi() {
  // UI-only reset; server session persists (for demo).
  renderMetaGrid($("uploadMeta"), []);
  renderMetaGrid($("processMeta"), []);
  renderWarnings([]);

  $("previewThead").innerHTML = "";
  $("previewTbody").innerHTML = "";

  $("csvFile").value = "";

  buildOptions($("dateColumn"), [], {});
  buildOptions($("usageColumn"), [], {});
  buildOptions($("regionColumn"), [], { includeBlank: true, blankLabel: "None" });

  setDisabled($("dateColumn"), true);
  setDisabled($("usageColumn"), true);
  setDisabled($("usageUnit"), true);
  setDisabled($("regionColumn"), true);
  setDisabled($("processBtn"), true);

  $("configHint").textContent = "Upload a CSV to unlock";

  $("kpiAvg").textContent = "—";
  $("kpiMax").textContent = "—";
  $("kpiTotal").textContent = "—";
  $("kpiAnoms").textContent = "—";

  const regionFilter = $("regionFilter");
  if (regionFilter) {
    regionFilter.innerHTML = `<option value="">All</option>`;
    setDisabled(regionFilter, true);
  }
  setDisabled($("refreshBtn"), true);

  $("alertsList").innerHTML = "";
  setHidden($("alertsEmpty"), true);
  setHidden($("metaSmall"), true);

  if (chart) {
    chart.data.labels = [];
    chart.data.datasets[0].data = [];
    chart.data.datasets[1].data = [];
    chart.update();
  }
}

async function main() {
  // Connectivity + session bootstrap
  const health = await fetchJson("/api/health");
  setConnectivityBadge(health.ok);
  if (!health.ok) {
    showToast(health.json?.detail || "Backend not reachable. Start the server and reload.", "error");
  }

  await refreshDebug();

  // Wire upload
  $("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("csvFile").files?.[0] || null;
    await handleUpload(file);
    await refreshDebug();
  });

  $("loadDemoBtn").addEventListener("click", async () => {
    const blob = makeDemoCsvBlob();
    const file = new File([blob], "voltsurge-demo.csv", { type: "text/csv" });
    await handleUpload(file);
    await refreshDebug();
  });

  // Wire processing
  $("configForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    await handleProcessSelection();
    await refreshDebug();
  });

  // Wire dashboard controls
  $("refreshBtn").addEventListener("click", async () => {
    await loadDashboard();
    await refreshDebug();
  });

  $("regionFilter").addEventListener("change", async () => {
    // Auto-refresh on filter change
    await loadDashboard();
  });

  $("resetBtn").addEventListener("click", () => {
    resetUi();
    showToast("UI reset (server session unchanged).", "info");
  });

  // If the session already has a processed dataset (e.g., after refresh), enable dashboard quickly.
  // Use payload_keys rather than trying to infer deep structure from payload_preview.
  const status = await fetchJson("/api/dataset/status");
  const keys = status.json?.payload_keys || [];
  const hasProcessedKey = Array.isArray(keys) && keys.includes("processed");
  if (hasProcessedKey) {
    showToast("Session already has processed data. Click Refresh to load dashboard.", "info");
    setDisabled($("refreshBtn"), false);
  }
}

main().catch((e) => {
  console.error(e);
  showToast("Unexpected frontend error. Check console.", "error");
});
