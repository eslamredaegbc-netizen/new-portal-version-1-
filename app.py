from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from monitoring_app.config import (
    APP_NAME,
    COPYRIGHT_NOTICE,
    DEFAULT_PASSWORD,
    DEFAULT_SOURCE_SELECTION,
    DEFAULT_USERNAME,
    OPEN_SOURCE_MODEL_RECOMMENDATION,
    OWNER_NAME,
    SOURCE_LABELS,
)
from monitoring_app.models import SearchOptions
from monitoring_app.services.ai_assistant import InternalAssistantService
from monitoring_app.services.llm_service import OpenSourceLLMService
from monitoring_app.services.pipeline import MonitoringPipeline
from monitoring_app.services.report_service import ReportService
from monitoring_app.storage import DatabaseManager
from monitoring_app.utils.text import compact_text, split_lines_to_list


st.set_page_config(
    page_title=APP_NAME,
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_services():
    repository = DatabaseManager()
    repository.initialize()
    return {
        "repository": repository,
        "pipeline": MonitoringPipeline(repository),
        "report_service": ReportService(repository),
        "assistant_service": InternalAssistantService(repository),
        "llm_service": OpenSourceLLMService(),
    }


SERVICES = get_services()
REPOSITORY: DatabaseManager = SERVICES["repository"]
PIPELINE: MonitoringPipeline = SERVICES["pipeline"]
REPORT_SERVICE: ReportService = SERVICES["report_service"]
ASSISTANT_SERVICE: InternalAssistantService = SERVICES["assistant_service"]
LLM_SERVICE: OpenSourceLLMService = SERVICES["llm_service"]


def ensure_state() -> None:
    defaults = {
        "authenticated": False,
        "user": None,
        "active_page": "لوحة التحكم",
        "search_bundle": None,
        "latest_search_id": None,
        "result_selection": {},
        "last_report": None,
        "assistant_response": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if st.session_state.latest_search_id and not st.session_state.search_bundle:
        bundle = REPOSITORY.get_search_bundle(int(st.session_state.latest_search_id))
        if bundle:
            st.session_state.search_bundle = bundle
            st.session_state.result_selection = {
                int(item["id"]): st.session_state.result_selection.get(int(item["id"]), True)
                for item in bundle["results"]
            }


def inject_css() -> None:
    st.markdown(
        """
        <style>
            :root {
                --surface: #ffffff;
                --surface-soft: #fffaf0;
                --surface-muted: #f7f4ec;
                --line: #e8dcc2;
                --gold: #b08a2b;
                --gold-soft: #e8d19a;
                --text: #111111;
                --muted: #5a5a5a;
                --danger: #b42318;
                --warning: #a15c00;
                --success: #027a48;
            }

            .stApp {
                background:
                    radial-gradient(circle at top right, rgba(232, 209, 154, 0.30), transparent 24%),
                    linear-gradient(180deg, #fffdf8 0%, #ffffff 52%, #fffdf7 100%);
                color: var(--text);
            }

            .block-container {
                padding-top: 1.4rem;
                padding-bottom: 2rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #ffffff 0%, #fffaf0 100%);
                border-left: 1px solid var(--line);
            }

            [data-testid="stSidebar"] * {
                color: var(--text);
            }

            .app-shell {
                background: rgba(255, 255, 255, 0.82);
                border: 1px solid rgba(232, 220, 194, 0.72);
                border-radius: 24px;
                padding: 1.4rem;
                box-shadow: 0 24px 80px rgba(17, 17, 17, 0.06);
                backdrop-filter: blur(14px);
            }

            .hero-card {
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(255, 248, 233, 0.92));
                border: 1px solid var(--line);
                border-radius: 24px;
                padding: 1.5rem 1.6rem;
                box-shadow: 0 20px 60px rgba(176, 138, 43, 0.08);
                margin-bottom: 1rem;
            }

            .hero-eyebrow {
                color: var(--gold);
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 0.5rem;
                font-weight: 700;
            }

            .hero-title {
                color: var(--text);
                font-size: 2rem;
                line-height: 1.35;
                margin: 0 0 0.45rem 0;
                font-weight: 800;
            }

            .hero-copy {
                color: var(--muted);
                font-size: 1rem;
                margin: 0;
                line-height: 1.9;
            }

            .metric-card {
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: 20px;
                padding: 1rem 1.05rem;
                min-height: 136px;
                box-shadow: 0 10px 30px rgba(17, 17, 17, 0.04);
            }

            .metric-label {
                color: var(--muted);
                font-size: 0.92rem;
                margin-bottom: 0.65rem;
            }

            .metric-value {
                color: var(--text);
                font-size: 2rem;
                font-weight: 800;
                margin-bottom: 0.45rem;
            }

            .metric-caption {
                color: var(--gold);
                font-size: 0.88rem;
                font-weight: 600;
            }

            .section-card {
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid var(--line);
                border-radius: 22px;
                padding: 1.15rem 1.2rem;
                box-shadow: 0 14px 40px rgba(17, 17, 17, 0.04);
                margin-bottom: 1rem;
            }

            .section-title {
                font-size: 1.15rem;
                font-weight: 800;
                color: var(--text);
                margin-bottom: 0.35rem;
            }

            .section-copy {
                color: var(--muted);
                line-height: 1.8;
                font-size: 0.96rem;
            }

            .chip {
                display: inline-block;
                border-radius: 999px;
                padding: 0.28rem 0.72rem;
                font-size: 0.82rem;
                font-weight: 700;
                margin-inline-start: 0.3rem;
                border: 1px solid transparent;
            }

            .chip-neutral {
                background: #f6f1e5;
                border-color: #ead9b0;
                color: #7d5c08;
            }

            .chip-red {
                background: #fef3f2;
                border-color: #fecdca;
                color: var(--danger);
            }

            .chip-yellow {
                background: #fffaeb;
                border-color: #fedf89;
                color: var(--warning);
            }

            .chip-green {
                background: #ecfdf3;
                border-color: #abefc6;
                color: var(--success);
            }

            .result-card {
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: 18px;
                padding: 1rem;
                margin-bottom: 0.75rem;
            }

            .result-title {
                color: var(--text);
                font-weight: 800;
                margin-bottom: 0.35rem;
                line-height: 1.7;
            }

            .result-meta {
                color: var(--muted);
                font-size: 0.9rem;
                line-height: 1.8;
            }

            .auth-shell {
                max-width: 540px;
                margin: 8vh auto 0 auto;
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid var(--line);
                border-radius: 28px;
                padding: 2rem 2rem 1.5rem 2rem;
                box-shadow: 0 30px 90px rgba(17, 17, 17, 0.08);
            }

            .auth-title {
                font-size: 1.9rem;
                font-weight: 800;
                color: var(--text);
                margin-bottom: 0.35rem;
            }

            .auth-copy {
                color: var(--muted);
                line-height: 1.9;
                margin-bottom: 1rem;
            }

            .footer-note {
                color: var(--muted);
                text-align: center;
                margin-top: 1rem;
                font-size: 0.85rem;
            }

            .stButton > button, .stDownloadButton > button {
                border-radius: 999px;
                border: 1px solid #d7be7f;
                background: linear-gradient(180deg, #d9b85f 0%, #b08a2b 100%);
                color: #111111;
                font-weight: 700;
                box-shadow: 0 10px 24px rgba(176, 138, 43, 0.16);
            }

            .stButton > button:hover, .stDownloadButton > button:hover {
                border-color: #b08a2b;
                color: #111111;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 0.4rem;
            }

            .stTabs [data-baseweb="tab"] {
                background: rgba(255, 250, 240, 0.8);
                border: 1px solid var(--line);
                border-radius: 999px;
                color: var(--text);
                padding: 0.45rem 0.95rem;
            }

            .stDataFrame, .stTable {
                border: 1px solid var(--line);
                border-radius: 18px;
                overflow: hidden;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def html_text(value: object) -> str:
    return escape(str(value or ""))


def render_hero(title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-eyebrow">{OWNER_NAME}</div>
            <div class="hero-title">{html_text(title)}</div>
            <p class="hero-copy">{html_text(copy)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: object, caption: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{html_text(label)}</div>
            <div class="metric-value">{html_text(value)}</div>
            <div class="metric-caption">{html_text(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_card(title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="section-title">{html_text(title)}</div>
            <div class="section-copy">{html_text(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(label: str, tone: str = "neutral") -> str:
    return f'<span class="chip chip-{tone}">{html_text(label)}</span>'


def tone_for_color(color_code: str) -> str:
    if color_code == "red":
        return "red"
    if color_code == "green":
        return "green"
    if color_code == "yellow":
        return "yellow"
    return "neutral"


def current_bundle() -> Dict | None:
    bundle = st.session_state.search_bundle
    if bundle:
        return bundle
    search_id = st.session_state.latest_search_id
    if not search_id:
        return None
    bundle = REPOSITORY.get_search_bundle(int(search_id))
    if bundle:
        st.session_state.search_bundle = bundle
    return bundle


def current_selected_ids(results: List[Dict]) -> List[int]:
    selection = st.session_state.result_selection or {}
    selected_ids = [int(item["id"]) for item in results if selection.get(int(item["id"]), False)]
    return selected_ids


def set_selection(results: List[Dict], selected: bool) -> None:
    st.session_state.result_selection = {int(item["id"]): selected for item in results}


def result_table(results: List[Dict]) -> pd.DataFrame:
    selection = st.session_state.result_selection or {}
    rows = []
    for item in results:
        result_id = int(item["id"])
        rows.append(
            {
                "selected": selection.get(result_id, True),
                "result_id": result_id,
                "priority": item.get("color_label", ""),
                "source": item.get("source_name", ""),
                "classification": item.get("classification", ""),
                "risk_score": int(item.get("risk_score") or 0),
                "title": compact_text(str(item.get("title", "")), 100),
                "domain": item.get("domain", ""),
                "url": item.get("url", ""),
            }
        )
    return pd.DataFrame(rows)


def filtered_results(results: List[Dict], color_filter: str, source_filter: List[str], text_filter: str) -> List[Dict]:
    filtered = results
    if color_filter != "الكل":
        mapping = {"أحمر": "red", "أصفر": "yellow", "أخضر": "green"}
        filtered = [item for item in filtered if item.get("color_code") == mapping.get(color_filter)]
    if source_filter:
        filtered = [item for item in filtered if item.get("source_name") in source_filter]
    if text_filter.strip():
        term = text_filter.strip().lower()
        filtered = [
            item
            for item in filtered
            if term in str(item.get("title", "")).lower()
            or term in str(item.get("snippet", "")).lower()
            or term in str(item.get("domain", "")).lower()
        ]
    return filtered


def render_login() -> None:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(
            f"""
            <div class="auth-shell">
                <div class="hero-eyebrow">{OWNER_NAME}</div>
                <div class="auth-title">{APP_NAME}</div>
                <div class="auth-copy">
                    نسخة تشغيل متوافقة مع Streamlit لتفعيل الرصد والبحث والتقارير من داخل نفس النظام
                    مع واجهة بيضاء سهلة وسريعة الاستخدام.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم", value=DEFAULT_USERNAME)
            password = st.text_input("كلمة المرور", type="password", value=DEFAULT_PASSWORD)
            submitted = st.form_submit_button("تسجيل الدخول")

        if submitted:
            user = REPOSITORY.authenticate_user(username.strip(), password)
            if not user:
                st.error("بيانات الدخول غير صحيحة.")
            else:
                st.session_state.authenticated = True
                st.session_state.user = user
                st.rerun()

        st.markdown(
            f'<div class="footer-note">{COPYRIGHT_NOTICE}</div>',
            unsafe_allow_html=True,
        )


def render_sidebar() -> str:
    user = st.session_state.user or {}
    google_enabled = PIPELINE.search_service.google_service.is_configured
    llm_metadata = LLM_SERVICE.metadata()

    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(f"{user.get('full_name', 'مستخدم النظام')} | {user.get('role', 'admin')}")
        st.markdown(
            badge("Google Web مفعل" if google_enabled else "Google Web غير مضبوط", "green" if google_enabled else "yellow")
            + badge("LLM خارجي مفعل" if llm_metadata.get("configured") else "LLM اختياري", "neutral"),
            unsafe_allow_html=True,
        )
        page = st.radio(
            "التنقل",
            ["لوحة التحكم", "البحث والرصد", "تقارير الرصد", "اسأل الذكاء الاصطناعي"],
            key="active_page",
        )

        bundle = current_bundle()
        if bundle:
            st.markdown("---")
            st.markdown("#### البحث الحالي")
            st.write(bundle["search"].get("query", ""))
            st.caption(f"عدد النتائج: {len(bundle['results'])} | القضايا: {len(bundle['cases'])}")
            st.caption(f"المصادر المختارة للتقرير: {len(current_selected_ids(bundle['results']))}")

        if st.button("تسجيل الخروج", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.search_bundle = None
            st.session_state.latest_search_id = None
            st.session_state.result_selection = {}
            st.session_state.last_report = None
            st.session_state.assistant_response = None
            st.rerun()

    return page


def render_dashboard() -> None:
    snapshot = REPOSITORY.dashboard_snapshot()
    metrics = snapshot.get("metrics", {})
    render_hero(
        "لوحة تحكم تنفيذية لسير الرصد",
        "تعرض هذه الصفحة الحالة العامة للنظام، حجم الرصد المنفذ، القضايا الأعلى حساسية، وأحدث التقارير والعمليات بشكل سريع وواضح.",
    )

    metric_columns = st.columns(4)
    metric_values = [
        ("إجمالي القضايا", metrics.get("total_cases", 0), "حالات مدمجة داخل قاعدة البيانات"),
        ("إجمالي النتائج", metrics.get("total_results", 0), "نتائج مفهرسة وقابلة للاختيار"),
        ("الحالات العالية", metrics.get("high_risk_cases", 0), "قضايا بدرجة خطورة مرتفعة"),
        ("التقارير", metrics.get("total_reports", 0), "تقارير صدرت فعليًا من النظام"),
    ]
    for column, item in zip(metric_columns, metric_values):
        with column:
            render_metric_card(*item)

    color_columns = st.columns(3)
    color_metrics = [
        ("نتائج حمراء", metrics.get("red_results", 0), "مؤشرات شكوى أو استغاثة أو نقد حاد"),
        ("نتائج صفراء", metrics.get("yellow_results", 0), "محتوى محايد أو منخفض الحساسية"),
        ("نتائج خضراء", metrics.get("green_results", 0), "إشادة أو محتوى إيجابي"),
    ]
    for column, item in zip(color_columns, color_metrics):
        with column:
            render_metric_card(*item)

    left, right = st.columns([1.1, 0.9])
    with left:
        render_section_card(
            "توصية النموذج المفتوح",
            (
                f"التوصية الحالية حتى {OPEN_SOURCE_MODEL_RECOMMENDATION['recommended_as_of']} هي "
                f"{OPEN_SOURCE_MODEL_RECOMMENDATION['text_model']} للنصوص و"
                f"{OPEN_SOURCE_MODEL_RECOMMENDATION['multimodal_model']} للوسائط المتعددة."
            ),
        )
        categories_df = pd.DataFrame(snapshot.get("categories", []))
        if not categories_df.empty:
            st.markdown("#### توزيع القضايا")
            chart_df = categories_df.set_index("category")
            st.bar_chart(chart_df, use_container_width=True)
        else:
            st.info("لا توجد بيانات قضايا كافية بعد لعرض التوزيع.")

    with right:
        sources_df = pd.DataFrame(snapshot.get("sources", []))
        if not sources_df.empty:
            st.markdown("#### توزيع المصادر")
            chart_df = sources_df.set_index("source_type")
            st.bar_chart(chart_df, use_container_width=True)
        else:
            st.info("لم تسجل مصادر بعد.")

    latest_searches = pd.DataFrame(snapshot.get("latest_searches", []))
    recent_reports = pd.DataFrame(snapshot.get("recent_reports", []))
    table_left, table_right = st.columns(2)
    with table_left:
        st.markdown("#### آخر عمليات البحث")
        if latest_searches.empty:
            st.info("لا توجد عمليات بحث مسجلة بعد.")
        else:
            st.dataframe(latest_searches, use_container_width=True, hide_index=True)
    with table_right:
        st.markdown("#### آخر التقارير")
        if recent_reports.empty:
            st.info("لا توجد تقارير صادرة بعد.")
        else:
            st.dataframe(recent_reports, use_container_width=True, hide_index=True)


def run_search(
    query: str,
    search_reason: str,
    google_dork: str,
    enabled_sources: List[str],
    include_terms: str,
    exclude_terms: str,
    official_domains: str,
    direct_urls: str,
    max_results_per_source: int,
    fetch_full_text: bool,
    enable_ocr: bool,
    enable_video_transcript: bool,
    search_images: bool,
) -> None:
    options = SearchOptions(
        enabled_sources=enabled_sources or list(DEFAULT_SOURCE_SELECTION),
        search_reason=search_reason.strip(),
        google_dork=google_dork.strip(),
        include_terms=split_lines_to_list(include_terms),
        exclude_terms=split_lines_to_list(exclude_terms),
        official_domains=split_lines_to_list(official_domains),
        direct_urls=split_lines_to_list(direct_urls),
        max_results_per_source=max(3, min(max_results_per_source, 12)),
        fetch_full_text=fetch_full_text,
        enable_ocr=enable_ocr,
        enable_video_transcript=enable_video_transcript,
        search_images=search_images,
    )
    outcome = PIPELINE.execute_search(query.strip(), options)

    if LLM_SERVICE.is_configured and outcome["results"]:
        llm_summary = LLM_SERVICE.summarize_sources(
            prompt=(
                f"موضوع الرصد: {query.strip()}. سبب البحث: {search_reason.strip()}. "
                "اكتب خلاصة مهنية قصيرة تستند فقط إلى الأدلة المتاحة."
            ),
            evidence_items=[
                {
                    "title": item.title,
                    "classification": item.classification,
                    "risk_score": str(item.risk_score),
                    "summary": item.legal_summary,
                    "url": item.url,
                }
                for item in outcome["results"][:10]
            ],
        )
        if llm_summary:
            outcome["insights"]["overall_summary"] = llm_summary
            REPOSITORY.finalize_search(outcome["search_id"], llm_summary, outcome["insights"]["source_analysis"])

    bundle = REPOSITORY.get_search_bundle(int(outcome["search_id"]))
    st.session_state.latest_search_id = int(outcome["search_id"])
    st.session_state.search_bundle = bundle
    st.session_state.result_selection = {
        int(item["id"]): True for item in (bundle["results"] if bundle else [])
    }
    st.session_state.last_report = None


def render_search_page() -> None:
    render_hero(
        "بحث متعدد المصادر مع تفسير لخطة البحث",
        "أدخل موضوع الرصد وسبب البحث، وسيبني النظام خطة بحث مفسرة تشمل الأخبار والمواقع الرسمية والمنصات العامة وGoogle Dorking والروابط المباشرة.",
    )

    with st.form("search_form"):
        query = st.text_input("موضوع البحث", placeholder="مثال: أزمة انقطاع الخدمة في القاهرة")
        search_reason = st.text_area("سبب البحث", height=120, placeholder="اشرح الهدف من الرصد حتى يبني النظام معايير بحث أدق.")
        google_dork = st.text_input("Google Dorking", placeholder='مثال: site:facebook.com "اسم الجهة"')
        enabled_sources = st.multiselect(
            "المصادر",
            options=list(SOURCE_LABELS.keys()),
            default=list(DEFAULT_SOURCE_SELECTION),
            format_func=lambda key: SOURCE_LABELS.get(key, key),
        )

        field_left, field_right = st.columns(2)
        with field_left:
            include_terms = st.text_area("كلمات يجب تضمينها", height=110, placeholder="كل كلمة في سطر مستقل")
            official_domains = st.text_area("نطاقات رسمية", height=110, placeholder="example.gov.eg")
        with field_right:
            exclude_terms = st.text_area("كلمات يجب استبعادها", height=110, placeholder="كل كلمة في سطر مستقل")
            direct_urls = st.text_area("روابط مباشرة", height=110, placeholder="https://...")

        toggles_a, toggles_b, toggles_c, toggles_d = st.columns(4)
        with toggles_a:
            max_results_per_source = st.slider("حد النتائج لكل مصدر", min_value=3, max_value=12, value=6)
        with toggles_b:
            fetch_full_text = st.toggle("جلب النص الكامل", value=True)
        with toggles_c:
            enable_video_transcript = st.toggle("استخراج نص الفيديو", value=True)
        with toggles_d:
            search_images = st.toggle("بحث الصور", value=True)

        enable_ocr = st.toggle("تشغيل OCR للصور", value=False)
        submitted = st.form_submit_button("ابدأ الرصد")

    if submitted:
        if len(query.strip()) < 2:
            st.error("أدخل موضوع بحث صالحًا قبل التنفيذ.")
        else:
            try:
                with st.spinner("يتم تنفيذ الرصد وبناء النتائج الآن..."):
                    run_search(
                        query=query,
                        search_reason=search_reason,
                        google_dork=google_dork,
                        enabled_sources=enabled_sources,
                        include_terms=include_terms,
                        exclude_terms=exclude_terms,
                        official_domains=official_domains,
                        direct_urls=direct_urls,
                        max_results_per_source=max_results_per_source,
                        fetch_full_text=fetch_full_text,
                        enable_ocr=enable_ocr,
                        enable_video_transcript=enable_video_transcript,
                        search_images=search_images,
                    )
                st.success("اكتمل الرصد وحُفظت النتائج داخل النظام.")
            except Exception as exc:
                st.error(f"تعذر تنفيذ البحث: {exc}")

    bundle = current_bundle()
    if not bundle:
        render_section_card(
            "لا توجد نتائج بعد",
            "نفذ أول عملية رصد من النموذج أعلاه، وبعدها ستظهر هنا القضايا، النتائج، خطة البحث، والتحليل المجمّع للمصادر.",
        )
        return

    search = bundle["search"]
    results = bundle["results"]
    cases = bundle["cases"]
    selected_ids = current_selected_ids(results)

    summary_cols = st.columns(4)
    summary_values = [
        ("النتائج الحالية", len(results), "تم حفظها في قاعدة البيانات"),
        ("القضايا المدمجة", len(cases), "دمج تلقائي للنتائج المتشابهة"),
        ("المصادر المختارة", len(selected_ids), "ستدخل في تقرير الرصد"),
        ("معرّف البحث", search.get("id", st.session_state.latest_search_id), "للرجوع إلى نفس العملية"),
    ]
    for column, item in zip(summary_cols, summary_values):
        with column:
            render_metric_card(*item)

    if search.get("overall_summary"):
        render_section_card("تحليل المصادر", search.get("overall_summary", ""))

    tab_results, tab_cases, tab_plan = st.tabs(["النتائج", "القضايا", "خطة البحث"])

    with tab_results:
        action_left, action_mid, action_right = st.columns([1, 1, 2])
        with action_left:
            if st.button("تحديد كل النتائج", key="select_all_results", use_container_width=True):
                set_selection(results, True)
                st.rerun()
        with action_mid:
            if st.button("إلغاء تحديد الكل", key="clear_all_results", use_container_width=True):
                set_selection(results, False)
                st.rerun()
        with action_right:
            st.caption("حدد النتائج التي تريد إبقاءها في تقرير الرصد النهائي. جميع الاختيارات تُحفظ للجلسة الحالية.")

        editor_df = result_table(results)
        edited_df = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            key=f"result_editor_{search.get('id', 'latest')}",
            column_config={
                "selected": st.column_config.CheckboxColumn("إدراج"),
                "result_id": st.column_config.NumberColumn("المعرف"),
                "priority": st.column_config.TextColumn("اللون"),
                "source": st.column_config.TextColumn("المصدر"),
                "classification": st.column_config.TextColumn("التصنيف"),
                "risk_score": st.column_config.NumberColumn("الخطورة"),
                "title": st.column_config.TextColumn("العنوان", width="large"),
                "domain": st.column_config.TextColumn("النطاق"),
                "url": st.column_config.LinkColumn("الرابط", display_text="فتح"),
            },
            disabled=["result_id", "priority", "source", "classification", "risk_score", "title", "domain", "url"],
        )
        st.session_state.result_selection = {
            int(row["result_id"]): bool(row["selected"]) for _, row in edited_df.iterrows()
        }

        filter_left, filter_mid, filter_right = st.columns([1, 1, 2])
        with filter_left:
            color_filter = st.selectbox("فلترة اللون", ["الكل", "أحمر", "أصفر", "أخضر"])
        with filter_mid:
            source_names = sorted({item.get("source_name", "") for item in results if item.get("source_name")})
            source_filter = st.multiselect("فلترة المصدر", options=source_names)
        with filter_right:
            text_filter = st.text_input("بحث داخل النتائج", placeholder="عنوان، وصف، أو نطاق")

        for item in filtered_results(results, color_filter, source_filter, text_filter):
            tone = tone_for_color(item.get("color_code", ""))
            st.markdown(
                f"""
                <div class="result-card">
                    <div class="result-title">{html_text(item.get("title", ""))}</div>
                    <div class="result-meta">
                        {badge(item.get("color_label", "غير محدد"), tone)}
                        {badge(item.get("classification", "غير مصنف"), "neutral")}
                        {badge(f"خطورة {int(item.get('risk_score') or 0)}/100", tone)}
                        <br />
                        المصدر: {html_text(item.get("source_name", ""))} | النطاق: {html_text(item.get("domain", ""))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("تفاصيل النتيجة"):
                meta_left, meta_right = st.columns(2)
                with meta_left:
                    st.write(f"الاستعلام المستخدم: {item.get('query_used', '') or 'غير متاح'}")
                    st.write(f"سبب الظهور: {item.get('query_reason', '') or 'غير متاح'}")
                    st.write(f"المؤلف: {item.get('author', '') or 'غير متاح'}")
                with meta_right:
                    st.write(f"التصنيف: {item.get('classification', '')}")
                    st.write(f"درجة الخطورة: {int(item.get('risk_score') or 0)}/100")
                    st.write(f"درجة الصلة: {item.get('relevance_score', 0)}")

                st.markdown("**الملخص القانوني التحفظي**")
                st.write(item.get("legal_summary", "") or "غير متاح")
                st.markdown("**رأي النظام**")
                st.write(item.get("analyst_opinion", "") or "غير متاح")
                st.markdown("**المقتطف**")
                st.write(item.get("snippet", "") or item.get("content_text", "") or "لا يوجد نص مقتطف.")
                if item.get("url"):
                    st.link_button("فتح الرابط الأصلي", item["url"])

    with tab_cases:
        if not cases:
            st.info("لم تتكون قضايا مدمجة بعد.")
        else:
            for case in cases:
                tone = tone_for_color(case.get("color_code", ""))
                st.markdown(
                    f"""
                    <div class="section-card">
                        <div class="section-title">{html_text(case.get("title", ""))}</div>
                        <div class="section-copy">
                            {badge(case.get("color_label", "محايد"), tone)}
                            {badge(case.get("primary_category", "غير محدد"), "neutral")}
                            {badge(f"خطورة {int(case.get('risk_score') or 0)}/100", tone)}
                            <br /><br />
                            {html_text(case.get("summary", ""))}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with tab_plan:
        criteria = search.get("criteria", {})
        plan_items = search.get("plan", [])
        render_section_card("سبب البحث", search.get("search_reason", "") or "لم يضف سبب بحث.")
        if criteria:
            st.markdown("#### معايير التنفيذ")
            st.json(criteria)
        if plan_items:
            st.markdown("#### خطة البحث")
            st.dataframe(pd.DataFrame(plan_items), use_container_width=True, hide_index=True)
        source_analysis = search.get("source_analysis", [])
        if source_analysis:
            st.markdown("#### تحليل المصادر حسب النوع")
            st.dataframe(pd.DataFrame(source_analysis), use_container_width=True, hide_index=True)


def render_reports_page() -> None:
    render_hero(
        "إصدار تقارير فعلية من المصادر المختارة فقط",
        "اختر النتائج التي تريد إدراجها، ثم أنشئ تقرير PDF أو DOCX أو CSV أو JSON مع حفظه داخل قاعدة البيانات وأرشيف التقارير.",
    )

    bundle = current_bundle()
    if bundle:
        results = bundle["results"]
        selected_ids = current_selected_ids(results)
        selected_rows = [item for item in results if int(item["id"]) in selected_ids]
        metrics_cols = st.columns(3)
        with metrics_cols[0]:
            render_metric_card("المحدد للتقرير", len(selected_ids), "نتائج ستدخل في التقرير")
        with metrics_cols[1]:
            render_metric_card(
                "أعلى خطورة",
                max([int(item.get("risk_score") or 0) for item in selected_rows], default=0),
                "أعلى درجة داخل المصادر المحددة",
            )
        with metrics_cols[2]:
            render_metric_card("البحث المرتبط", bundle["search"].get("id", ""), bundle["search"].get("query", ""))

        default_title = f"تقرير رصد - {bundle['search'].get('query', 'بحث')}"
        default_summary = bundle["search"].get("overall_summary", "")
        with st.form("report_form"):
            report_title = st.text_input("عنوان التقرير", value=default_title)
            executive_summary = st.text_area("الملخص التنفيذي", value=default_summary, height=180)
            format_name = st.selectbox("صيغة التقرير", ["pdf", "docx", "csv", "json"])
            generate = st.form_submit_button("إصدار التقرير")

        if generate:
            if not selected_ids:
                st.error("حدد نتيجة واحدة على الأقل قبل إصدار التقرير.")
            else:
                try:
                    with st.spinner("يتم إنشاء التقرير وحفظه الآن..."):
                        report = REPORT_SERVICE.generate_report(
                            format_name=format_name,
                            report_title=report_title.strip() or "تقرير رصد",
                            search_id=int(bundle["search"]["id"]),
                            selected_result_ids=selected_ids,
                            executive_summary=executive_summary.strip(),
                        )
                    st.session_state.last_report = report
                    st.success(f"تم إنشاء التقرير بنجاح: {report['file_name']}")
                except Exception as exc:
                    st.error(f"تعذر إنشاء التقرير: {exc}")

    else:
        render_section_card(
            "لا يوجد بحث نشط مرتبط بالتقارير",
            "نفذ عملية رصد أولًا، ثم اختر المصادر التي تريد إدراجها في التقرير النهائي من صفحة البحث والرصد.",
        )

    if st.session_state.last_report:
        report = st.session_state.last_report
        report_path = Path(report["file_path"])
        if report_path.exists():
            render_section_card(
                "آخر تقرير تم إنشاؤه",
                f"{report['file_name']} | الصيغة: {report['format']} | المصادر المدرجة: {report['selected_results_count']}",
            )
            st.download_button(
                "تحميل آخر تقرير",
                data=report_path.read_bytes(),
                file_name=report_path.name,
                mime="application/octet-stream",
                key=f"latest_report_download_{report['report_id']}",
                use_container_width=True,
            )

    st.markdown("#### أرشيف التقارير")
    reports = REPOSITORY.list_reports()
    if not reports:
        st.info("لا توجد تقارير محفوظة بعد.")
        return

    for report in reports:
        report_path = Path(report["file_path"])
        col_info, col_action = st.columns([4, 1])
        with col_info:
            render_section_card(
                report.get("report_title", report.get("report_name", "تقرير")),
                (
                    f"الصيغة: {report.get('format', '')} | "
                    f"المصادر المدرجة: {report.get('selected_results_count', 0)} | "
                    f"تاريخ الإنشاء: {report.get('created_at', '')}"
                ),
            )
        with col_action:
            if report_path.exists():
                st.download_button(
                    "تحميل",
                    data=report_path.read_bytes(),
                    file_name=report_path.name,
                    mime="application/octet-stream",
                    key=f"download_report_{report['id']}",
                    use_container_width=True,
                )
            else:
                st.warning("الملف غير موجود")


def render_assistant_page() -> None:
    render_hero(
        "اسأل الذكاء الاصطناعي داخل حدود بيانات النظام",
        "الإجابات هنا لا تعتمد على الإنترنت مباشرة، بل على القضايا والنتائج المحفوظة داخل النظام فقط، مع عرض الأدلة ودرجة الثقة.",
    )

    with st.form("assistant_form"):
        question = st.text_area("اكتب سؤالك", height=140, placeholder="مثال: ما أبرز القضايا عالية الخطورة المتعلقة بموضوع البحث الأخير؟")
        ask = st.form_submit_button("تحليل السؤال")

    if ask:
        if len(question.strip()) < 2:
            st.error("اكتب سؤالًا أوضح حتى يتمكن النظام من الإجابة.")
        else:
            with st.spinner("يتم تحليل السؤال داخل بيانات النظام..."):
                st.session_state.assistant_response = ASSISTANT_SERVICE.answer_question(question.strip())

    answer = st.session_state.assistant_response
    if not answer:
        render_section_card(
            "لا توجد إجابة بعد",
            "بعد طرح سؤال، سيعرض النظام الإجابة المختصرة، ونطاق البيانات الذي اعتمد عليه، وأهم الأدلة الداعمة.",
        )
        return

    metric_cols = st.columns(2)
    with metric_cols[0]:
        render_metric_card("الثقة", answer.confidence, "تقدير داخلي مبني على تشابه البيانات")
    with metric_cols[1]:
        render_metric_card("نطاق البيانات", answer.data_scope, "عدد القضايا والسجلات الداخلة في الفحص")

    render_section_card("الإجابة", answer.answer)
    st.markdown("#### الأدلة")
    if not answer.evidence:
        st.info("لم يعثر النظام على أدلة كافية لعرضها.")
    else:
        for item in answer.evidence:
            st.markdown(
                f"""
                <div class="result-card">
                    <div class="result-title">{html_text(item.title)}</div>
                    <div class="result-meta">
                        {badge(f"القضية #{item.case_id}", "neutral")}
                        {badge(f"تشابه {item.similarity}", "yellow")}
                        <br /><br />
                        {html_text(item.snippet)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if item.url:
                st.link_button("فتح المصدر المرتبط", item.url, key=f"assistant_link_{item.case_id}_{item.similarity}")


def main() -> None:
    ensure_state()
    inject_css()

    if not st.session_state.authenticated:
        render_login()
        return

    st.markdown('<div class="app-shell">', unsafe_allow_html=True)
    page = render_sidebar()
    if page == "لوحة التحكم":
        render_dashboard()
    elif page == "البحث والرصد":
        render_search_page()
    elif page == "تقارير الرصد":
        render_reports_page()
    else:
        render_assistant_page()
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
