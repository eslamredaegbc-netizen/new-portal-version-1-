from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from monitoring_app.config import SOURCE_LABELS
from monitoring_app.models import SearchPlanItem, SearchResult
from monitoring_app.services.google_search_service import GoogleProgrammableSearchService
from monitoring_app.services.media_service import PageMediaService
from monitoring_app.utils.text import dedupe_urls, extract_domain


TEXT_SOURCES = {"web", "official", "facebook", "instagram", "forums"}


class MultiSourceSearchService:
    def __init__(self) -> None:
        self.media_service = PageMediaService()
        self.google_service = GoogleProgrammableSearchService()

    def run(
        self,
        plan_items: List[SearchPlanItem],
        fetch_options: Dict[str, object],
        direct_urls: List[str],
        max_results_per_source: int,
    ) -> List[SearchResult]:
        unique_urls = set()
        collected: List[SearchResult] = []
        source_counts = defaultdict(int)

        for plan_item in plan_items:
            remaining = max_results_per_source - source_counts[plan_item.source_type]
            if remaining <= 0:
                continue

            query_limit = self._query_limit(plan_item.source_type, remaining)
            for raw_result in self._run_plan_item(plan_item, max_results=query_limit):
                unique_key = (raw_result.url or raw_result.title).strip().lower()
                if not unique_key or unique_key in unique_urls:
                    continue
                unique_urls.add(unique_key)

                enrichment = self.media_service.enrich_result(
                    raw_result.url,
                    fetch_full_text=bool(fetch_options.get("fetch_full_text", True)),
                    enable_ocr=bool(fetch_options.get("enable_ocr", False)),
                    enable_video_transcript=bool(fetch_options.get("enable_video_transcript", True)),
                    source_type=raw_result.source_type,
                )
                raw_result.content_text = str(enrichment.get("content_text", ""))
                raw_result.transcript = str(enrichment.get("transcript", ""))
                raw_result.ocr_text = str(enrichment.get("ocr_text", ""))
                raw_result.media_urls = list(enrichment.get("media_urls", []))
                collected.append(raw_result)
                source_counts[raw_result.source_type] += 1

                if source_counts[raw_result.source_type] >= max_results_per_source:
                    break

        for raw_result in self._load_direct_urls(direct_urls):
            unique_key = (raw_result.url or raw_result.title).strip().lower()
            if not unique_key or unique_key in unique_urls:
                continue
            unique_urls.add(unique_key)

            enrichment = self.media_service.enrich_result(
                raw_result.url,
                fetch_full_text=bool(fetch_options.get("fetch_full_text", True)),
                enable_ocr=bool(fetch_options.get("enable_ocr", False)),
                enable_video_transcript=bool(fetch_options.get("enable_video_transcript", True)),
                source_type=raw_result.source_type,
            )
            raw_result.content_text = str(enrichment.get("content_text", ""))
            raw_result.transcript = str(enrichment.get("transcript", ""))
            raw_result.ocr_text = str(enrichment.get("ocr_text", ""))
            raw_result.media_urls = list(enrichment.get("media_urls", []))
            collected.append(raw_result)

        return collected

    def _run_plan_item(self, plan_item: SearchPlanItem, max_results: int) -> Iterable[SearchResult]:
        if plan_item.source_type in TEXT_SOURCES:
            yield from self._search_text(plan_item, max_results=max_results)
        elif plan_item.source_type == "news":
            yield from self._search_news(plan_item, max_results=max_results)
        elif plan_item.source_type == "youtube":
            yield from self._search_videos(plan_item, max_results=max_results)
        elif plan_item.source_type == "images":
            yield from self._search_images(plan_item, max_results=max_results)

    def _query_limit(self, source_type: str, remaining: int) -> int:
        base_limit = 2 if source_type in {"images", "youtube"} else 3
        return max(1, min(remaining, base_limit))

    def _search_text(self, plan_item: SearchPlanItem, max_results: int) -> Iterable[SearchResult]:
        if self.google_service.is_configured:
            for item in self.google_service.search_text(plan_item.query, max_results=max_results):
                url = item.get("link", "").strip()
                yield SearchResult(
                    source_type=plan_item.source_type,
                    source_name=SOURCE_LABELS[plan_item.source_type],
                    platform=SOURCE_LABELS[plan_item.source_type],
                    title=item.get("title", "").strip(),
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    domain=extract_domain(url),
                    query_used=plan_item.query,
                    query_reason=f"{plan_item.explanation} | مزود البحث: Google Web",
                    raw_payload={"search_engine": "google", **dict(item)},
                )

        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.text(plan_item.query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    url = item.get("href", "").strip()
                    yield SearchResult(
                        source_type=plan_item.source_type,
                        source_name=SOURCE_LABELS[plan_item.source_type],
                        platform=SOURCE_LABELS[plan_item.source_type],
                        title=item.get("title", "").strip(),
                        url=url,
                        snippet=item.get("body", "").strip(),
                        domain=extract_domain(url),
                        query_used=plan_item.query,
                        query_reason=f"{plan_item.explanation} | مزود البحث: DuckDuckGo Web",
                        raw_payload={"search_engine": "duckduckgo", **dict(item)},
                    )
        except Exception:
            return

    def _search_news(self, plan_item: SearchPlanItem, max_results: int) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.news(plan_item.query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    url = item.get("url", "").strip()
                    yield SearchResult(
                        source_type="news",
                        source_name=SOURCE_LABELS["news"],
                        platform="News",
                        title=item.get("title", "").strip(),
                        url=url,
                        snippet=item.get("body", "").strip(),
                        domain=extract_domain(url),
                        published_at=item.get("date", "") or "",
                        author=item.get("source", "") or "",
                        query_used=plan_item.query,
                        query_reason=f"{plan_item.explanation} | مزود البحث: DuckDuckGo News",
                        raw_payload={"search_engine": "duckduckgo_news", **dict(item)},
                    )
        except Exception:
            return

    def _search_videos(self, plan_item: SearchPlanItem, max_results: int) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.videos(plan_item.query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    url = item.get("content", "").strip() or item.get("url", "").strip()
                    images = item.get("images", {})
                    if isinstance(images, dict):
                        media_urls = dedupe_urls([images.get("large", ""), images.get("small", "")])
                    elif isinstance(images, list):
                        media_urls = dedupe_urls(images)
                    elif isinstance(images, str):
                        media_urls = dedupe_urls([images])
                    else:
                        media_urls = []

                    yield SearchResult(
                        source_type="youtube",
                        source_name=SOURCE_LABELS["youtube"],
                        platform="YouTube",
                        title=item.get("title", "").strip(),
                        url=url,
                        snippet=item.get("description", "").strip(),
                        domain=extract_domain(url),
                        published_at=item.get("published", "") or "",
                        author=item.get("publisher", "") or "",
                        media_urls=media_urls,
                        query_used=plan_item.query,
                        query_reason=f"{plan_item.explanation} | مزود البحث: DuckDuckGo Videos",
                        raw_payload={"search_engine": "duckduckgo_videos", **dict(item)},
                    )
        except Exception:
            return

    def _search_images(self, plan_item: SearchPlanItem, max_results: int) -> Iterable[SearchResult]:
        if self.google_service.is_configured:
            for item in self.google_service.search_images(plan_item.query, max_results=max_results):
                image_info = item.get("image", {}) if isinstance(item.get("image"), dict) else {}
                image_url = item.get("link", "").strip()
                source_url = image_info.get("contextLink", "").strip()
                yield SearchResult(
                    source_type="images",
                    source_name=SOURCE_LABELS["images"],
                    platform="Images",
                    title=item.get("title", "").strip() or "صورة مرتبطة بموضوع البحث",
                    url=image_url or source_url,
                    snippet=item.get("snippet", "").strip(),
                    domain=extract_domain(source_url or image_url),
                    media_urls=dedupe_urls([image_url, image_info.get("thumbnailLink", "")]),
                    query_used=plan_item.query,
                    query_reason=f"{plan_item.explanation} | مزود البحث: Google Images",
                    raw_payload={"search_engine": "google_images", **dict(item)},
                )

        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.images(plan_item.query, max_results=max_results, safesearch="moderate")
                for item in results:
                    image_url = item.get("image", "").strip()
                    source_url = item.get("url", "").strip() or image_url
                    yield SearchResult(
                        source_type="images",
                        source_name=SOURCE_LABELS["images"],
                        platform="Images",
                        title=item.get("title", "").strip() or "صورة مرتبطة بموضوع البحث",
                        url=image_url or source_url,
                        snippet=item.get("source", "").strip(),
                        domain=extract_domain(source_url),
                        media_urls=dedupe_urls([image_url, item.get("thumbnail", "")]),
                        query_used=plan_item.query,
                        query_reason=f"{plan_item.explanation} | مزود البحث: DuckDuckGo Images",
                        raw_payload={"search_engine": "duckduckgo_images", **dict(item)},
                    )
        except Exception:
            return

    def _load_direct_urls(self, urls: List[str]) -> Iterable[SearchResult]:
        for url in dedupe_urls(urls):
            yield SearchResult(
                source_type="direct",
                source_name=SOURCE_LABELS["direct"],
                platform="Direct",
                title=f"رابط مباشر: {extract_domain(url) or url}",
                url=url,
                snippet="رابط مباشر أدخله العضو ضمن عملية الرصد.",
                domain=extract_domain(url),
                query_used=url,
                query_reason="أضيف هذا الرابط يدويًا لضمان عدم فقدان مصدر معروف مسبقًا.",
                raw_payload={"mode": "direct", "search_engine": "manual"},
            )
