from __future__ import annotations

from pathlib import Path
from typing import List, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from monitoring_app.api_helpers import serialize_cases, serialize_plan_items, serialize_results
from monitoring_app.config import APP_NAME, DEFAULT_SOURCE_SELECTION, OPEN_SOURCE_MODEL_RECOMMENDATION, STATIC_DIR
from monitoring_app.models import SearchOptions
from monitoring_app.services.ai_assistant import InternalAssistantService
from monitoring_app.services.llm_service import OpenSourceLLMService
from monitoring_app.services.pipeline import MonitoringPipeline
from monitoring_app.services.report_service import ReportService
from monitoring_app.storage import DatabaseManager
from monitoring_app.utils.text import split_lines_to_list


class LoginRequest(BaseModel):
    username: str
    password: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    search_reason: str = ""
    google_dork: str = ""
    enabled_sources: List[str] = Field(default_factory=lambda: list(DEFAULT_SOURCE_SELECTION))
    include_terms: Union[str, List[str]] = Field(default_factory=list)
    exclude_terms: Union[str, List[str]] = Field(default_factory=list)
    official_domains: Union[str, List[str]] = Field(default_factory=list)
    direct_urls: Union[str, List[str]] = Field(default_factory=list)
    max_results_per_source: int = 6
    fetch_full_text: bool = True
    enable_ocr: bool = False
    enable_video_transcript: bool = True
    search_images: bool = True


class AssistantRequest(BaseModel):
    question: str = Field(..., min_length=2)


class ReportRequest(BaseModel):
    search_id: int
    report_title: str
    selected_result_ids: List[int]
    executive_summary: str = ""
    format_name: str


repository = DatabaseManager()
repository.initialize()
pipeline = MonitoringPipeline(repository)
report_service = ReportService(repository)
assistant_service = InternalAssistantService(repository)
llm_service = OpenSourceLLMService()

app = FastAPI(title=APP_NAME)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _to_list(value: Union[str, List[str]]) -> List[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if str(item).strip()]
    return split_lines_to_list(value)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME}


@app.get("/api/system/model")
def system_model() -> dict:
    return {
        "recommended_open_source_model": OPEN_SOURCE_MODEL_RECOMMENDATION,
        "configured_model": llm_service.metadata(),
        "accuracy_note": (
            "لا يمكن لأي نظام رصد ضمان دقة 100% أو صفر أخطاء على الويب المفتوح، "
            "لكن النظام يطبق تعدد مصادر وخطة بحث مفسرة وتحليلًا تحفظيًا لرفع الدقة وتقليل الخطأ."
        ),
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    user = repository.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة.")
    return {"success": True, "user": user}


@app.get("/api/dashboard")
def dashboard() -> dict:
    return repository.dashboard_snapshot()


@app.post("/api/search")
def search(payload: SearchRequest) -> dict:
    options = SearchOptions(
        enabled_sources=payload.enabled_sources or list(DEFAULT_SOURCE_SELECTION),
        search_reason=payload.search_reason.strip(),
        google_dork=payload.google_dork.strip(),
        include_terms=_to_list(payload.include_terms),
        exclude_terms=_to_list(payload.exclude_terms),
        official_domains=_to_list(payload.official_domains),
        direct_urls=_to_list(payload.direct_urls),
        max_results_per_source=max(3, min(payload.max_results_per_source, 12)),
        fetch_full_text=payload.fetch_full_text,
        enable_ocr=payload.enable_ocr,
        enable_video_transcript=payload.enable_video_transcript,
        search_images=payload.search_images,
    )
    outcome = pipeline.execute_search(payload.query.strip(), options)

    if llm_service.is_configured and outcome["results"]:
        llm_summary = llm_service.summarize_sources(
            prompt=(
                f"موضوع الرصد: {payload.query}. سبب البحث: {payload.search_reason}. "
                "أعطني خلاصة تحليل مصادر قانونية مهنية مختصرة."
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
            repository.finalize_search(outcome["search_id"], llm_summary, outcome["insights"]["source_analysis"])

    stored_bundle = repository.get_search_bundle(outcome["search_id"])
    return {
        "search_id": outcome["search_id"],
        "plan": {
            "criteria": outcome["plan"]["criteria"],
            "explanation": outcome["plan"]["explanation"],
            "items": serialize_plan_items(outcome["plan"]["items"]),
        },
        "insights": outcome["insights"],
        "cases": stored_bundle["cases"] if stored_bundle else serialize_cases(outcome["cases"]),
        "results": stored_bundle["results"] if stored_bundle else serialize_results(outcome["results"]),
    }


@app.get("/api/searches/{search_id}")
def get_search(search_id: int) -> dict:
    bundle = repository.get_search_bundle(search_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="تعذر العثور على عملية البحث.")
    return bundle


@app.post("/api/reports")
def create_report(payload: ReportRequest) -> dict:
    if not payload.selected_result_ids:
        raise HTTPException(status_code=400, detail="اختر مصدرًا واحدًا على الأقل للتقرير.")
    try:
        report = report_service.generate_report(
            format_name=payload.format_name.lower(),
            report_title=payload.report_title.strip() or "تقرير رصد",
            search_id=payload.search_id,
            selected_result_ids=payload.selected_result_ids,
            executive_summary=payload.executive_summary.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report


@app.get("/api/reports")
def list_reports() -> dict:
    return {"reports": repository.list_reports()}


@app.get("/api/reports/{report_id}")
def get_report(report_id: int) -> dict:
    report = repository.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="التقرير غير موجود.")
    return report


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: int):
    report = repository.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="التقرير غير موجود.")
    file_path = Path(report["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ملف التقرير غير موجود على الخادم.")
    return FileResponse(path=str(file_path), filename=file_path.name)


@app.post("/api/assistant")
def ask_assistant(payload: AssistantRequest) -> dict:
    answer = assistant_service.answer_question(payload.question.strip())
    return {
        "answer": answer.answer,
        "confidence": answer.confidence,
        "data_scope": answer.data_scope,
        "evidence": [
            {
                "case_id": item.case_id,
                "title": item.title,
                "url": item.url,
                "snippet": item.snippet,
                "similarity": item.similarity,
            }
            for item in answer.evidence
        ],
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
