from __future__ import annotations

from typing import Dict, List

from monitoring_app.models import SearchOptions, SearchResult
from monitoring_app.services.case_service import CaseManagementService
from monitoring_app.services.content_analysis import ContentAnalysisService
from monitoring_app.services.insight_service import InsightService
from monitoring_app.services.search_planner import SearchPlannerService
from monitoring_app.services.source_service import MultiSourceSearchService
from monitoring_app.storage import DatabaseManager


class MonitoringPipeline:
    def __init__(self, repository: DatabaseManager) -> None:
        self.repository = repository
        self.analysis_service = ContentAnalysisService()
        self.search_planner = SearchPlannerService()
        self.search_service = MultiSourceSearchService()
        self.case_service = CaseManagementService(self.analysis_service)
        self.insight_service = InsightService()

    def execute_search(self, query: str, options: SearchOptions) -> Dict[str, object]:
        plan_payload = self.search_planner.build_plan(query, options)
        results = self.search_service.run(
            plan_items=plan_payload["items"],
            fetch_options={
                "fetch_full_text": options.fetch_full_text,
                "enable_ocr": options.enable_ocr,
                "enable_video_transcript": options.enable_video_transcript,
            },
            direct_urls=options.direct_urls,
            max_results_per_source=options.max_results_per_source,
        )
        analyzed_results: List[SearchResult] = [
            self.analysis_service.analyze_result(result, query, options.search_reason) for result in results
        ]

        search_id = self.repository.create_search(query, options, plan_payload, len(analyzed_results))
        existing_cases = self.repository.list_case_anchors()
        cases = self.case_service.build_cases(analyzed_results, existing_cases)
        for case in cases:
            case_id = self.repository.save_case_bundle(search_id, case)
            case.case_id = case_id
            for result in case.results:
                result.case_id = case_id

        insights = self.insight_service.build_source_analysis(analyzed_results, options.search_reason)
        self.repository.finalize_search(search_id, insights["overall_summary"], insights["source_analysis"])

        return {
            "search_id": search_id,
            "plan": plan_payload,
            "insights": insights,
            "results": analyzed_results,
            "cases": cases,
        }
