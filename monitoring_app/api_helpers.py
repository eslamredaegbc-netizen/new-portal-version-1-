from __future__ import annotations

from typing import Dict, List

from monitoring_app.models import CaseRecord, SearchPlanItem, SearchResult


def serialize_plan_items(items: List[SearchPlanItem]) -> List[Dict]:
    return [
        {
            "source_type": item.source_type,
            "query": item.query,
            "explanation": item.explanation,
            "strategy": item.strategy,
        }
        for item in items
    ]


def serialize_results(results: List[SearchResult]) -> List[Dict]:
    return [
        {
            "result_id": getattr(item, "result_id", None),
            "case_id": item.case_id,
            "source_type": item.source_type,
            "source_name": item.source_name,
            "platform": item.platform,
            "title": item.title,
            "url": item.url,
            "domain": item.domain,
            "snippet": item.snippet,
            "published_at": item.published_at,
            "author": item.author,
            "query_used": item.query_used,
            "query_reason": item.query_reason,
            "classification": item.classification,
            "classification_confidence": item.classification_confidence,
            "risk_score": item.risk_score,
            "relevance_score": item.relevance_score,
            "color_code": item.color_code,
            "color_label": item.color_label,
            "legal_summary": item.legal_summary,
            "analyst_opinion": item.analyst_opinion,
            "matched_signals": item.matched_signals,
            "media_urls": item.media_urls,
        }
        for item in results
    ]


def serialize_cases(cases: List[CaseRecord]) -> List[Dict]:
    return [
        {
            "case_id": case.case_id,
            "title": case.title,
            "summary": case.summary,
            "primary_category": case.primary_category,
            "risk_score": case.risk_score,
            "confidence": case.confidence,
            "color_code": case.color_code,
            "color_label": case.color_label,
            "source_mix": case.source_mix,
            "results_count": len(case.results),
        }
        for case in cases
    ]
