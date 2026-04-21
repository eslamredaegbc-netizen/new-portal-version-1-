from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from monitoring_app.models import CaseRecord, SearchResult
from monitoring_app.services.content_analysis import ContentAnalysisService
from monitoring_app.utils.text import compact_text, normalize_text


class CaseManagementService:
    def __init__(self, analysis_service: ContentAnalysisService) -> None:
        self.analysis_service = analysis_service

    def build_cases(self, results: List[SearchResult], existing_cases: List[Dict]) -> List[CaseRecord]:
        groups: List[Dict[str, object]] = []

        for result in sorted(results, key=lambda item: (item.risk_score, item.relevance_score), reverse=True):
            fingerprint = self._fingerprint(result)
            matched_group: Optional[Dict[str, object]] = None
            best_similarity = 0.0

            for group in groups:
                group_fingerprint = str(group["fingerprint"])
                similarity = self.analysis_service.similarity(fingerprint, group_fingerprint)
                same_url = result.url and result.url == group.get("canonical_url")
                if same_url:
                    similarity = 1.0
                if similarity > best_similarity:
                    best_similarity = similarity
                    matched_group = group

            if matched_group and best_similarity >= 0.68:
                if best_similarity >= 0.9 or (result.url and result.url == matched_group.get("canonical_url")):
                    result.classification = "مكرر"
                    result.color_code = "yellow"
                    result.color_label = "محايد"
                    result.risk_score = max(5, result.risk_score - 25)
                    result.duplicate_of = int(matched_group["anchor_index"])
                    result.matched_signals = list(dict.fromkeys(result.matched_signals + ["مطابقة عالية مع نتيجة سابقة"]))
                matched_group["results"].append(result)
                if result.risk_score > int(matched_group["risk_score"]):
                    matched_group["risk_score"] = result.risk_score
                continue

            groups.append(
                {
                    "results": [result],
                    "fingerprint": fingerprint,
                    "canonical_url": result.url,
                    "anchor_index": len(groups) + 1,
                    "risk_score": result.risk_score,
                }
            )

        case_records: List[CaseRecord] = []
        for group in groups:
            group_results = list(group["results"])
            primary = self._select_primary(group_results)
            primary_category = self.analysis_service.dominant_category(group_results)
            source_mix = self._source_mix(group_results)
            case = CaseRecord(
                title=compact_text(primary.title or "قضية بدون عنوان", 140),
                summary=self.analysis_service.summarize_cluster(group_results),
                primary_category=primary_category,
                risk_score=max(item.risk_score for item in group_results),
                confidence=self.analysis_service.average_confidence(group_results),
                canonical_text=str(group["fingerprint"]),
                canonical_url=str(group["canonical_url"] or primary.url),
                source_mix=source_mix,
                color_code=primary.color_code,
                color_label=primary.color_label,
                results=group_results,
            )
            case.case_id = self._match_existing_case(case, existing_cases)
            case_records.append(case)
        return case_records

    def _select_primary(self, results: List[SearchResult]) -> SearchResult:
        non_duplicate = [item for item in results if item.classification != "مكرر"]
        ranked = non_duplicate or results
        return sorted(ranked, key=lambda item: (item.risk_score, item.relevance_score), reverse=True)[0]

    def _fingerprint(self, result: SearchResult) -> str:
        return normalize_text(
            " ".join(
                [
                    result.title,
                    result.snippet,
                    result.content_text[:700],
                    result.transcript[:600],
                    result.ocr_text[:300],
                ]
            )
        )

    def _source_mix(self, results: List[SearchResult]) -> Dict[str, int]:
        counter = Counter(result.source_type for result in results)
        return dict(counter)

    def _match_existing_case(self, case: CaseRecord, existing_cases: List[Dict]) -> Optional[int]:
        best_case_id: Optional[int] = None
        best_score = 0.0
        for existing in existing_cases:
            if case.canonical_url and case.canonical_url == existing.get("canonical_url"):
                return int(existing["id"])
            similarity = self.analysis_service.similarity(case.canonical_text, existing.get("canonical_text", ""))
            if similarity > best_score:
                best_score = similarity
                best_case_id = int(existing["id"])
        if best_score >= 0.76:
            return best_case_id
        return None

