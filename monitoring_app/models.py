from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class SearchPlanItem:
    source_type: str
    query: str
    explanation: str
    strategy: str


@dataclass(slots=True)
class SearchOptions:
    enabled_sources: List[str]
    search_reason: str = ""
    google_dork: str = ""
    include_terms: List[str] = field(default_factory=list)
    exclude_terms: List[str] = field(default_factory=list)
    official_domains: List[str] = field(default_factory=list)
    direct_urls: List[str] = field(default_factory=list)
    max_results_per_source: int = 6
    fetch_full_text: bool = True
    enable_ocr: bool = False
    enable_video_transcript: bool = True
    search_images: bool = True
    language: str = "ar"


@dataclass(slots=True)
class SearchResult:
    source_type: str
    source_name: str
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    published_at: str = ""
    author: str = ""
    platform: str = ""
    query_used: str = ""
    query_reason: str = ""
    content_text: str = ""
    transcript: str = ""
    ocr_text: str = ""
    media_urls: List[str] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    classification: str = "خبر محايد"
    classification_confidence: float = 0.0
    risk_score: int = 0
    relevance_score: float = 0.0
    color_code: str = "yellow"
    color_label: str = "محايد"
    legal_summary: str = ""
    analyst_opinion: str = ""
    duplicate_of: Optional[int] = None
    matched_signals: List[str] = field(default_factory=list)
    case_id: Optional[int] = None

    @property
    def combined_text(self) -> str:
        parts = [self.title, self.snippet, self.content_text, self.transcript, self.ocr_text]
        return " ".join(part for part in parts if part).strip()


@dataclass(slots=True)
class CaseRecord:
    title: str
    summary: str
    primary_category: str
    risk_score: int
    confidence: float
    canonical_text: str
    canonical_url: str
    source_mix: Dict[str, int]
    color_code: str = "yellow"
    color_label: str = "محايد"
    results: List[SearchResult] = field(default_factory=list)
    case_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(slots=True)
class AssistantEvidence:
    case_id: int
    title: str
    url: str
    snippet: str
    similarity: float


@dataclass(slots=True)
class AssistantAnswer:
    answer: str
    confidence: float
    evidence: List[AssistantEvidence]
    data_scope: str

