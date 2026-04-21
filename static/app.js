const state = {
  user: null,
  currentSearch: null,
  selectedResultIds: new Set(),
  generatedReports: [],
  dashboardSnapshot: null,
  reportsArchive: [],
  systemModel: null,
  resultView: {
    tone: "all",
    text: "",
    sort: "risk_desc",
  },
};

const SOURCE_LABELS = {
  web: "الويب العام",
  news: "الأخبار",
  official: "المواقع الرسمية",
  facebook: "Facebook",
  instagram: "Instagram",
  youtube: "YouTube",
  forums: "المنتديات",
  images: "الصور",
  direct: "روابط مباشرة",
};

const loginScreen = document.getElementById("login-screen");
const appShell = document.getElementById("app-shell");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const userName = document.getElementById("user-name");
const navButtons = Array.from(document.querySelectorAll(".nav-btn"));

function qs(id) {
  return document.getElementById(id);
}

function qsa(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("ar-EG").format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "غير محدد";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat("ar-EG", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function resultId(item) {
  return Number(item.result_id ?? item.id);
}

function safeText(...values) {
  return values.find((item) => String(item || "").trim()) || "";
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    throw new Error("تعذر الاتصال بالنظام حاليًا. تحقق من تشغيل الخادم ثم أعد المحاولة.");
  }

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = isJson ? payload.detail || "حدث خطأ غير متوقع." : payload;
    throw new Error(detail);
  }
  return payload;
}

function setActiveSection(sectionId) {
  navButtons.forEach((button) => {
    const isActive = button.dataset.section === sectionId;
    button.classList.toggle("active", isActive);
  });
  qsa(".content-section").forEach((section) => {
    section.classList.toggle("hidden", section.id !== sectionId);
  });

  const activeButton = navButtons.find((button) => button.dataset.section === sectionId);
  if (activeButton) {
    qs("page-kicker").textContent = activeButton.textContent;
    qs("page-title").textContent = activeButton.dataset.title || activeButton.textContent;
    qs("page-subtitle").textContent = activeButton.dataset.subtitle || "";
  }
}

function showApp() {
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  userName.textContent = state.user?.full_name || "-";
}

function showLogin() {
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
}

function metricCard(title, value, note = "", accent = "gold") {
  return `
    <article class="metric-card accent-${escapeHtml(accent)}">
      <div class="metric-label">${escapeHtml(title)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-note">${escapeHtml(note)}</div>
    </article>
  `;
}

function pill(label, tone = "") {
  return `<span class="pill ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

function renderHeroPanel() {
  const metrics = state.dashboardSnapshot?.metrics || {};
  const model = state.systemModel?.recommended_open_source_model || {};
  const accuracyNote = state.systemModel?.accuracy_note || "";

  qs("command-center").innerHTML = `
    <div class="hero-grid">
      <div>
        <span class="eyebrow">مركز المتابعة</span>
        <h2>رؤية تشغيلية سريعة</h2>
        <p class="muted">
          الواجهة الآن مرتبة حول رحلة عمل واضحة: بدء البحث، فحص الأدلة، اختيار النتائج، ثم إصدار التقرير من المصادر المعتمدة فقط.
        </p>
        <div class="tag-row">
          ${pill(`إجمالي عمليات البحث ${formatNumber(metrics.total_searches || 0)}`)}
          ${pill(`نتائج حمراء ${formatNumber(metrics.red_results || 0)}`, "red")}
          ${pill(`نتائج صفراء ${formatNumber(metrics.yellow_results || 0)}`, "yellow")}
          ${pill(`نتائج خضراء ${formatNumber(metrics.green_results || 0)}`, "green")}
        </div>
      </div>
      <div class="detail-grid">
        <div class="detail-box">
          <strong>التوصية الحالية للنموذج</strong>
          <div>${escapeHtml(model.text_model || "غير متاح")}</div>
          <div class="muted">${escapeHtml(model.multimodal_model || "")}</div>
        </div>
        <div class="detail-box">
          <strong>ملاحظة الدقة</strong>
          <div class="muted">${escapeHtml(accuracyNote || "لا توجد ملاحظة حالية.")}</div>
        </div>
      </div>
    </div>
  `;
}

function renderStatList(items, labelKey) {
  if (!Array.isArray(items) || !items.length) {
    return '<div class="empty-state">لا توجد بيانات كافية بعد.</div>';
  }
  const maxValue = Math.max(...items.map((item) => Number(item.total || 0)), 1);
  return items
    .map((item) => {
      const total = Number(item.total || 0);
      const width = Math.max(8, (total / maxValue) * 100);
      return `
        <article class="stat-item">
          <div class="stat-line">
            <span>${escapeHtml(item[labelKey])}</span>
            <span>${formatNumber(total)}</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${width}%"></div>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderDashboard(snapshot) {
  state.dashboardSnapshot = snapshot;
  const metrics = snapshot.metrics || {};
  renderHeroPanel();

  qs("dashboard-metrics").innerHTML = [
    metricCard("إجمالي القضايا", formatNumber(metrics.total_cases || 0), "القضايا المدمجة داخل النظام", "gold"),
    metricCard("إجمالي النتائج", formatNumber(metrics.total_results || 0), "كل ما تم حفظه من نتائج بحث", "gold"),
    metricCard("القضايا عالية الخطورة", formatNumber(metrics.high_risk_cases || 0), "قضايا بدرجة 80 فأعلى", "red"),
    metricCard("إجمالي التقارير", formatNumber(metrics.total_reports || 0), "كل التقارير المخرجة والمحفوظة", "gold"),
    metricCard("نتائج حمراء", formatNumber(metrics.red_results || 0), "نتائج تحتاج انتباهًا أعلى", "red"),
    metricCard("نتائج خضراء", formatNumber(metrics.green_results || 0), "نتائج ذات طابع إيجابي أو إشادة", "green"),
  ].join("");

  const latestSearches = snapshot.latest_searches || [];
  qs("latest-searches").innerHTML = latestSearches.length
    ? latestSearches
        .map(
          (item) => `
            <article class="archive-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(item.query)}</h4>
                  <div class="card-subtitle">${escapeHtml(item.search_reason || "بدون سبب بحث إضافي.")}</div>
                </div>
                <div class="tag-row">
                  ${pill(`#${item.id}`)}
                  ${pill(`${formatNumber(item.total_results || 0)} نتيجة`)}
                </div>
              </div>
              <div class="muted small-text">${escapeHtml(formatDate(item.created_at))}</div>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لا توجد عمليات بحث بعد.</div>';

  const recentReports = snapshot.recent_reports || [];
  qs("dashboard-reports").innerHTML = recentReports.length
    ? recentReports
        .map(
          (item) => `
            <article class="archive-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(item.report_title || "تقرير بدون عنوان")}</h4>
                  <div class="card-subtitle">${escapeHtml(formatDate(item.created_at))}</div>
                </div>
                <div class="tag-row">
                  ${pill(item.format || "-")}
                  ${pill(`${formatNumber(item.selected_results_count || 0)} مصدر`)}
                </div>
              </div>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لا توجد تقارير بعد.</div>';

  qs("categories-breakdown").innerHTML = renderStatList(snapshot.categories || [], "category");
  qs("sources-breakdown").innerHTML = renderStatList(
    (snapshot.sources || []).map((item) => ({
      ...item,
      source_type: SOURCE_LABELS[item.source_type] || item.source_type,
    })),
    "source_type"
  );
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  renderDashboard(data);
}

function renderModelRecommendation() {
  const data = state.systemModel || {};
  const recommendation = data.recommended_open_source_model || {};
  qs("model-recommendation").innerHTML = `
    <article class="source-card">
      <div class="card-head">
        <div>
          <h4 class="card-title">التوصية حتى ${escapeHtml(recommendation.recommended_as_of || "-")}</h4>
          <div class="card-subtitle">${escapeHtml(recommendation.reason || "")}</div>
        </div>
      </div>
      <div class="detail-grid">
        <div class="detail-box">
          <strong>النموذج النصي</strong>
          <div>${escapeHtml(recommendation.text_model || "-")}</div>
        </div>
        <div class="detail-box">
          <strong>النموذج متعدد الوسائط</strong>
          <div>${escapeHtml(recommendation.multimodal_model || "-")}</div>
        </div>
      </div>
      <p class="muted">${escapeHtml(data.accuracy_note || "")}</p>
    </article>
  `;
}

async function loadModelRecommendation() {
  state.systemModel = await api("/api/system/model");
  renderModelRecommendation();
  if (state.dashboardSnapshot) {
    renderDashboard(state.dashboardSnapshot);
  }
}

function collectSearchPayload() {
  const form = qs("search-form");
  const formData = new FormData(form);
  return {
    query: formData.get("query"),
    search_reason: formData.get("search_reason"),
    google_dork: formData.get("google_dork"),
    include_terms: formData.get("include_terms"),
    exclude_terms: formData.get("exclude_terms"),
    official_domains: formData.get("official_domains"),
    direct_urls: formData.get("direct_urls"),
    max_results_per_source: Number(formData.get("max_results_per_source") || 6),
    enabled_sources: qsa('input[name="sources"]:checked').map((item) => item.value),
    fetch_full_text: form.querySelector('input[name="fetch_full_text"]').checked,
    enable_ocr: form.querySelector('input[name="enable_ocr"]').checked,
    enable_video_transcript: form.querySelector('input[name="enable_video_transcript"]').checked,
    search_images: form.querySelector('input[name="search_images"]').checked,
  };
}

function renderPlan(plan) {
  qs("plan-summary").innerHTML = `<article class="source-card">${escapeHtml(plan.explanation || "")}</article>`;
  const criteria = plan.criteria || {};
  const tags = [];

  if (criteria.topic) tags.push(pill(`الموضوع: ${criteria.topic}`));
  if (criteria.reason) tags.push(pill(`سبب البحث: ${criteria.reason}`));
  if (Array.isArray(criteria.sources)) {
    criteria.sources.forEach((item) => tags.push(pill(item)));
  }
  if (Array.isArray(criteria.focus_terms)) {
    criteria.focus_terms.slice(0, 6).forEach((item) => tags.push(pill(`إشارة: ${item}`)));
  }
  if (Array.isArray(criteria.excluded_terms) && criteria.excluded_terms.length) {
    criteria.excluded_terms.slice(0, 4).forEach((item) => tags.push(pill(`استبعاد: ${item}`)));
  }

  qs("plan-criteria").innerHTML = tags.join("");
  qs("plan-items").innerHTML = (plan.items || [])
    .map(
      (item) => `
        <article class="plan-card">
          <div class="card-head">
            <div>
                  <h4 class="card-title">${escapeHtml(SOURCE_LABELS[item.source_type] || item.source_type)}</h4>
              <div class="card-subtitle">${escapeHtml(item.strategy || "")}</div>
            </div>
          </div>
          <div class="detail-box">
            <strong>الاستعلام المستخدم</strong>
            <div>${escapeHtml(item.query)}</div>
          </div>
          <div class="detail-box">
            <strong>سبب هذا الاستعلام</strong>
            <div>${escapeHtml(item.explanation || "")}</div>
          </div>
        </article>
      `
    )
    .join("");
}

function renderInsights(insights) {
  qs("insights-summary").innerHTML = insights?.overall_summary
    ? `<article class="source-card">${escapeHtml(insights.overall_summary)}</article>`
    : '<div class="empty-state">لا يوجد تحليل مصادر بعد.</div>';

  qs("source-analysis-list").innerHTML = Array.isArray(insights?.source_analysis) && insights.source_analysis.length
    ? insights.source_analysis
        .map(
          (item) => `
            <article class="source-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(item.source_name)}</h4>
                  <div class="card-subtitle">${escapeHtml(item.summary || "")}</div>
                </div>
                <div class="tag-row">
                  ${pill(`${formatNumber(item.count || 0)} نتيجة`)}
                  ${pill(`أعلى خطورة ${formatNumber(item.highest_risk || 0)}`)}
                  ${pill(item.top_category || "-")}
                </div>
              </div>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لا يوجد تحليل تفصيلي للمصادر بعد.</div>';
}

function renderCases(cases) {
  qs("cases-container").innerHTML = Array.isArray(cases) && cases.length
    ? cases
        .map(
          (item) => `
            <article class="case-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(item.title)}</h4>
                  <div class="card-subtitle">${escapeHtml(item.summary || "")}</div>
                </div>
                <div class="tag-row">
                  ${pill(item.primary_category || "-")}
                  ${pill(`خطورة ${formatNumber(item.risk_score || 0)}`)}
                  ${pill(`ثقة ${item.confidence || 0}`)}
                </div>
              </div>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لا توجد قضايا مدمجة لهذه العملية.</div>';
}

function getCurrentResults() {
  return Array.isArray(state.currentSearch?.results) ? state.currentSearch.results : [];
}

function getSelectedResults() {
  return getCurrentResults().filter((item) => state.selectedResultIds.has(resultId(item)));
}

function getFilteredResults() {
  let results = [...getCurrentResults()];

  if (state.resultView.tone !== "all") {
    results = results.filter((item) => item.color_code === state.resultView.tone);
  }

  const filterText = state.resultView.text.trim().toLowerCase();
  if (filterText) {
    results = results.filter((item) =>
      [
        item.title,
        item.source_name,
        item.classification,
        item.legal_summary,
        item.analyst_opinion,
        item.snippet,
      ]
        .join(" ")
        .toLowerCase()
        .includes(filterText)
    );
  }

  if (state.resultView.sort === "relevance_desc") {
    results.sort((left, right) => Number(right.relevance_score || 0) - Number(left.relevance_score || 0));
  } else if (state.resultView.sort === "source_asc") {
    results.sort((left, right) => String(left.source_name || "").localeCompare(String(right.source_name || ""), "ar"));
  } else {
    results.sort((left, right) => Number(right.risk_score || 0) - Number(left.risk_score || 0));
  }

  return results;
}

function renderResultCard(item, selectable = true) {
  const id = resultId(item);
  const isChecked = state.selectedResultIds.has(id) ? "checked" : "";
  const matchedSignals = Array.isArray(item.matched_signals) ? item.matched_signals : [];

  return `
    <article class="result-card ${escapeHtml(item.color_code || "yellow")}">
      <div class="card-head">
        <div>
          <h4 class="card-title">${escapeHtml(item.title || "بدون عنوان")}</h4>
          <div class="card-subtitle">${escapeHtml(item.source_name || "-")} ${item.platform ? `| ${escapeHtml(item.platform)}` : ""}</div>
        </div>
        <div class="result-actions">
          ${selectable
            ? `
              <label class="result-selector-label">
                <input type="checkbox" class="result-selector" data-result-id="${id}" ${isChecked} />
                <span>إضافة للتقرير</span>
              </label>
            `
            : pill("محدد للتقرير")}
          ${item.url ? `<a class="external-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">فتح المصدر</a>` : ""}
        </div>
      </div>

      <div class="tag-row">
        ${pill(item.classification || "-")}
        ${pill(item.color_label || "-", item.color_code || "")}
        ${pill(`الخطورة ${formatNumber(item.risk_score || 0)}`)}
        ${pill(`الصلة ${item.relevance_score || 0}`)}
        ${item.author ? pill(`الناشر ${item.author}`) : ""}
        ${item.published_at ? pill(formatDate(item.published_at)) : ""}
      </div>

      <div class="detail-grid">
        <div class="detail-box">
          <strong>الملخص القانوني</strong>
          <div>${escapeHtml(safeText(item.legal_summary, item.snippet, "لا يوجد ملخص متاح."))}</div>
        </div>
        <div class="detail-box">
          <strong>رأي التحليل</strong>
          <div>${escapeHtml(safeText(item.analyst_opinion, "لا يوجد رأي تحليلي إضافي."))}</div>
        </div>
      </div>

      <div class="detail-grid">
        <div class="detail-box">
          <strong>سبب ظهور النتيجة</strong>
          <div>${escapeHtml(safeText(item.query_reason, "لم يسجل سبب الاستعلام."))}</div>
        </div>
        <div class="detail-box">
          <strong>الاستعلام المستخدم</strong>
          <div>${escapeHtml(safeText(item.query_used, "غير متاح"))}</div>
        </div>
      </div>

      ${
        matchedSignals.length
          ? `<div class="tag-row">${matchedSignals.slice(0, 6).map((signal) => pill(signal)).join("")}</div>`
          : ""
      }
    </article>
  `;
}

function renderResultsToolbar() {
  const allResults = getCurrentResults();
  const filteredResults = getFilteredResults();
  const redCount = allResults.filter((item) => item.color_code === "red").length;
  const yellowCount = allResults.filter((item) => item.color_code === "yellow").length;
  const greenCount = allResults.filter((item) => item.color_code === "green").length;

  qs("results-toolbar").innerHTML = `
    <div class="toolbar-row">
      <span class="selection-badge">المعروض ${formatNumber(filteredResults.length)} من أصل ${formatNumber(allResults.length)}</span>
      <button class="filter-chip ${state.resultView.tone === "all" ? "active" : ""}" data-tone="all">الكل</button>
      <button class="filter-chip ${state.resultView.tone === "red" ? "active" : ""}" data-tone="red">الأحمر ${formatNumber(redCount)}</button>
      <button class="filter-chip ${state.resultView.tone === "yellow" ? "active" : ""}" data-tone="yellow">الأصفر ${formatNumber(yellowCount)}</button>
      <button class="filter-chip ${state.resultView.tone === "green" ? "active" : ""}" data-tone="green">الأخضر ${formatNumber(greenCount)}</button>
    </div>
    <div class="toolbar-row">
      <input id="result-text-filter" type="text" placeholder="ابحث داخل النتائج المعروضة" value="${escapeHtml(state.resultView.text)}" />
      <select id="result-sort">
        <option value="risk_desc" ${state.resultView.sort === "risk_desc" ? "selected" : ""}>ترتيب حسب الخطورة</option>
        <option value="relevance_desc" ${state.resultView.sort === "relevance_desc" ? "selected" : ""}>ترتيب حسب الصلة</option>
        <option value="source_asc" ${state.resultView.sort === "source_asc" ? "selected" : ""}>ترتيب حسب المصدر</option>
      </select>
      <button id="select-visible-btn" class="ghost-btn">تحديد المعروض</button>
      <button id="clear-selection-btn" class="ghost-btn">إلغاء التحديد</button>
    </div>
  `;

  qsa(".filter-chip[data-tone]").forEach((button) => {
    button.addEventListener("click", () => {
      state.resultView.tone = button.dataset.tone;
      renderResultsSection();
    });
  });

  qs("result-text-filter").addEventListener("input", (event) => {
    state.resultView.text = event.target.value;
    renderResultsSection();
  });

  qs("result-sort").addEventListener("change", (event) => {
    state.resultView.sort = event.target.value;
    renderResultsSection();
  });

  qs("select-visible-btn").addEventListener("click", () => {
    getFilteredResults().forEach((item) => state.selectedResultIds.add(resultId(item)));
    renderResultsSection();
  });

  qs("clear-selection-btn").addEventListener("click", () => {
    state.selectedResultIds.clear();
    renderResultsSection();
  });
}

function bindResultSelectionHandlers() {
  qsa(".result-selector").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const id = Number(checkbox.dataset.resultId);
      if (checkbox.checked) {
        state.selectedResultIds.add(id);
      } else {
        state.selectedResultIds.delete(id);
      }
      renderSelectedResults();
    });
  });
}

function renderSelectedResults() {
  const selected = getSelectedResults();
  const redCount = selected.filter((item) => item.color_code === "red").length;
  const yellowCount = selected.filter((item) => item.color_code === "yellow").length;
  const greenCount = selected.filter((item) => item.color_code === "green").length;

  qs("selection-status").textContent = `${formatNumber(selected.length)} مصدر محدد`;
  qs("goto-report-btn").disabled = selected.length === 0;

  qs("selection-overview").innerHTML = selected.length
    ? [
        metricCard("المصادر المختارة", formatNumber(selected.length), "سيتم إدراجها في التقرير النهائي", "gold"),
        metricCard("أولوية حمراء", formatNumber(redCount), "نتائج تستلزم انتباهًا أعلى", "red"),
        metricCard("محايد", formatNumber(yellowCount), "نتائج محايدة أو أقل حساسية", "gold"),
        metricCard("إيجابي", formatNumber(greenCount), "نتائج الثناء والإشادة", "green"),
      ].join("")
    : "";

  qs("selected-results-container").innerHTML = selected.length
    ? selected.map((item) => renderResultCard(item, false)).join("")
    : '<div class="empty-state">لا توجد مصادر مختارة بعد.</div>';
}

function renderResultsSection() {
  const results = getCurrentResults();
  if (!results.length) {
    qs("results-toolbar").innerHTML = "نفذ عملية بحث أولًا لإظهار أدوات التصفية والاختيار.";
    qs("results-container").innerHTML = '<div class="empty-state">لا توجد نتائج بحث حالية.</div>';
    renderSelectedResults();
    return;
  }

  renderResultsToolbar();
  const filteredResults = getFilteredResults();
  qs("results-container").innerHTML = filteredResults.length
    ? filteredResults.map((item) => renderResultCard(item, true)).join("")
    : '<div class="empty-state">لا توجد نتائج مطابقة لعوامل التصفية الحالية.</div>';
  bindResultSelectionHandlers();
  renderSelectedResults();
}

function renderSearchOutcome(data) {
  state.currentSearch = data;
  state.resultView = { tone: "all", text: "", sort: "risk_desc" };
  state.selectedResultIds = new Set();
  renderPlan(data.plan || {});
  renderInsights(data.insights || {});
  renderCases(data.cases || []);
  renderResultsSection();
}

function renderGeneratedReports() {
  qs("generated-reports").innerHTML = state.generatedReports.length
    ? state.generatedReports
        .map(
          (report) => `
            <article class="archive-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(report.file_name)}</h4>
                  <div class="card-subtitle">${escapeHtml(report.summary || "تم إنشاء التقرير بنجاح.")}</div>
                </div>
                <div class="tag-row">
                  ${pill(report.format || "-")}
                  ${pill(`${formatNumber(report.selected_results_count || 0)} مصدر`)}
                </div>
              </div>
              <a class="external-link" href="/api/reports/${report.report_id}/download">تنزيل التقرير</a>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لم يتم توليد أي تقرير بعد.</div>';
}

function renderReportsArchive() {
  qs("reports-archive").innerHTML = state.reportsArchive.length
    ? state.reportsArchive
        .map(
          (report) => `
            <article class="archive-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(report.report_title || report.report_name || "تقرير")}</h4>
                  <div class="card-subtitle">${escapeHtml(report.summary || "بدون ملخص محفوظ.")}</div>
                </div>
                <div class="tag-row">
                  ${pill(report.format || "-")}
                  ${pill(`${formatNumber(report.selected_results_count || 0)} مصدر`)}
                </div>
              </div>
              <div class="muted small-text">${escapeHtml(formatDate(report.created_at))}</div>
              <a class="external-link" href="/api/reports/${report.id}/download">تنزيل</a>
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لا توجد تقارير بعد.</div>';
}

async function loadReportsArchive() {
  const payload = await api("/api/reports");
  state.reportsArchive = Array.isArray(payload.reports) ? payload.reports : [];
  renderReportsArchive();
}

async function refreshShellData() {
  const tasks = await Promise.allSettled([loadDashboard(), loadModelRecommendation(), loadReportsArchive()]);
  const rejected = tasks.find((item) => item.status === "rejected");
  if (rejected) {
    console.error(rejected.reason);
  }
}

function renderAssistantAnswer(data) {
  qs("assistant-answer").innerHTML = `
    <article class="source-card">
      <div class="card-head">
        <div>
          <h4 class="card-title">الإجابة</h4>
          <div class="card-subtitle">${escapeHtml(data.answer || "")}</div>
        </div>
        <div class="tag-row">
          ${pill(`الثقة ${data.confidence || 0}`)}
          ${pill(data.data_scope || "-")}
        </div>
      </div>
    </article>
  `;

  qs("assistant-evidence").innerHTML = Array.isArray(data.evidence) && data.evidence.length
    ? data.evidence
        .map(
          (item) => `
            <article class="archive-card">
              <div class="card-head">
                <div>
                  <h4 class="card-title">${escapeHtml(item.title || "دليل")}</h4>
                  <div class="card-subtitle">${escapeHtml(item.snippet || "")}</div>
                </div>
                <div class="tag-row">
                  ${pill(`#${item.case_id}`)}
                  ${pill(`التطابق ${item.similarity}`)}
                </div>
              </div>
              ${item.url ? `<a class="external-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">فتح المصدر</a>` : ""}
            </article>
          `
        )
        .join("")
    : '<div class="empty-state">لم يتم العثور على أدلة كافية.</div>';
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  const formData = new FormData(loginForm);
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
      }),
    });
    state.user = data.user;
    sessionStorage.setItem("monitoringUser", JSON.stringify(data.user));
    showApp();
    setActiveSection("dashboard-section");
    await refreshShellData();
  } catch (error) {
    loginError.textContent = error.message;
  }
});

qs("logout-btn").addEventListener("click", () => {
  sessionStorage.removeItem("monitoringUser");
  state.user = null;
  state.currentSearch = null;
  state.selectedResultIds = new Set();
  state.generatedReports = [];
  state.dashboardSnapshot = null;
  state.reportsArchive = [];
  state.systemModel = null;
  showLogin();
});

navButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveSection(button.dataset.section));
});

qs("quick-search-btn").addEventListener("click", () => setActiveSection("search-section"));
qs("quick-report-btn").addEventListener("click", () => setActiveSection("report-section"));
qs("refresh-dashboard-btn").addEventListener("click", loadDashboard);
qs("refresh-reports-btn").addEventListener("click", loadReportsArchive);
qs("goto-report-btn").addEventListener("click", () => setActiveSection("report-section"));

qs("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  qs("search-status").textContent = "جارٍ تنفيذ الرصد وتحليل النتائج...";

  try {
    const payload = collectSearchPayload();
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderSearchOutcome(data);
    qs("search-status").textContent = `تم العثور على ${formatNumber(data.results?.length || 0)} نتيجة قابلة للمراجعة.`;
    await loadDashboard();
  } catch (error) {
    qs("search-status").textContent = error.message;
  }
});

qsa(".export-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.currentSearch) {
      qs("report-status").textContent = "نفذ عملية بحث أولًا.";
      return;
    }

    const selectedIds = Array.from(state.selectedResultIds);
    if (!selectedIds.length) {
      qs("report-status").textContent = "اختر مصدرًا واحدًا على الأقل قبل إصدار التقرير.";
      return;
    }

    const formData = new FormData(qs("report-form"));
    qs("report-status").textContent = `جارٍ إصدار ${button.dataset.format.toUpperCase()}...`;

    try {
      const report = await api("/api/reports", {
        method: "POST",
        body: JSON.stringify({
          search_id: state.currentSearch.search_id,
          report_title: formData.get("report_title"),
          selected_result_ids: selectedIds,
          executive_summary: formData.get("executive_summary"),
          format_name: button.dataset.format,
        }),
      });
      state.generatedReports.unshift(report);
      renderGeneratedReports();
      qs("report-status").textContent = `تم إنشاء ${report.file_name} بنجاح.`;
      await loadReportsArchive();
    } catch (error) {
      qs("report-status").textContent = error.message;
    }
  });
});

qs("assistant-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(qs("assistant-form"));

  try {
    const data = await api("/api/assistant", {
      method: "POST",
      body: JSON.stringify({ question: formData.get("question") }),
    });
    renderAssistantAnswer(data);
  } catch (error) {
    qs("assistant-answer").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
});

async function bootstrap() {
  const savedUser = sessionStorage.getItem("monitoringUser");
  if (!savedUser) {
    showLogin();
    return;
  }

  try {
    state.user = JSON.parse(savedUser);
  } catch (error) {
    sessionStorage.removeItem("monitoringUser");
    showLogin();
    return;
  }

  showApp();
  setActiveSection("dashboard-section");
  await refreshShellData();
}

bootstrap();
