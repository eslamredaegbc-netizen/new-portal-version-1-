from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from monitoring_app.config import SOURCE_LABELS, USER_AGENT
from monitoring_app.models import SearchPlanItem, SearchResult
from monitoring_app.services.google_search_service import GoogleProgrammableSearchService
from monitoring_app.services.media_service import PageMediaService
from monitoring_app.services.news_search_service import GoogleNewsRssService
from monitoring_app.services.youtube_search_service import YouTubeDataSearchService
from monitoring_app.utils.text import dedupe_urls, extract_domain


TEXT_SOURCES = {"web", "official", "facebook", "instagram", "forums"}


class MultiSourceSearchService:
    def __init__(self) -> None:
        self.media_service = PageMediaService()
        self.google_service = GoogleProgrammableSearchService()
        self.news_service = GoogleNewsRssService()
        self.youtube_service = YouTubeDataSearchService()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def run(
        self,
        plan_items: List[SearchPlanItem],
        fetch_options: Dict[str, object],
        direct_urls: List[str],
        max_results_per_source: int,
    ) -> Dict[str, object]:
        unique_urls = set()
        collected: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []
        source_counts = defaultdict(int)

        for plan_item in plan_items:
            remaining = max_results_per_source - source_counts[plan_item.source_type]
            if remaining <= 0:
                continue

            query_limit = self._query_limit(plan_item.source_type, remaining)
            search_payload = self._run_plan_item(plan_item, max_results=query_limit)
            diagnostics.extend(search_payload["diagnostics"])

            for raw_result in search_payload["results"]:
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

        direct_results, direct_diagnostics = self._load_direct_urls(direct_urls)
        diagnostics.extend(direct_diagnostics)
        for raw_result in direct_results:
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

        return {
            "results": collected,
            "diagnostics": diagnostics,
        }

    def _run_plan_item(self, plan_item: SearchPlanItem, max_results: int) -> Dict[str, object]:
        if plan_item.source_type in TEXT_SOURCES:
            results, diagnostics = self._search_text(plan_item, max_results=max_results)
        elif plan_item.source_type == "news":
            results, diagnostics = self._search_news(plan_item, max_results=max_results)
        elif plan_item.source_type == "youtube":
            results, diagnostics = self._search_videos(plan_item, max_results=max_results)
        elif plan_item.source_type == "images":
            results, diagnostics = self._search_images(plan_item, max_results=max_results)
        else:
            results, diagnostics = [], []

        return {
            "results": results,
            "diagnostics": diagnostics,
        }

    def _query_limit(self, source_type: str, remaining: int) -> int:
        base_limit = 4 if source_type in {"images", "youtube"} else 5
        return max(1, min(remaining, base_limit))

    def _search_text(self, plan_item: SearchPlanItem, max_results: int) -> Tuple[List[SearchResult], List[Dict[str, object]]]:
        results: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []

        google_results, google_error = self.google_service.search_text(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "google_web", google_results, google_error))
        results.extend(
            self._make_text_results(
                plan_item=plan_item,
                items=google_results,
                provider_label="Google Web",
                provider_key="google",
                href_key="link",
                title_key="title",
                snippet_key="snippet",
            )
        )

        ddg_results, ddg_error = self._duckduckgo_text_search(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "duckduckgo_web", ddg_results, ddg_error))
        results.extend(
            self._make_text_results(
                plan_item=plan_item,
                items=ddg_results,
                provider_label="DuckDuckGo Web",
                provider_key="duckduckgo",
                href_key="href",
                title_key="title",
                snippet_key="body",
            )
        )

        if not google_results and not ddg_results:
            html_results, html_error = self._duckduckgo_html_search(plan_item.query, max_results=max_results)
            diagnostics.append(self._diagnostic(plan_item, "duckduckgo_html", html_results, html_error))
            results.extend(
                self._make_text_results(
                    plan_item=plan_item,
                    items=html_results,
                    provider_label="DuckDuckGo HTML",
                    provider_key="duckduckgo_html",
                    href_key="href",
                    title_key="title",
                    snippet_key="body",
                )
            )

        return results, diagnostics

    def _search_news(self, plan_item: SearchPlanItem, max_results: int) -> Tuple[List[SearchResult], List[Dict[str, object]]]:
        results: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []

        rss_results, rss_error = self.news_service.search_news(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "google_news_rss", rss_results, rss_error))
        for item in rss_results:
            url = item.get("url", "").strip()
            results.append(
                SearchResult(
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
                    query_reason=f"{plan_item.explanation} | مزود البحث: Google News RSS",
                    raw_payload={"search_engine": "google_news_rss", **dict(item)},
                )
            )

        ddg_results, ddg_error = self._duckduckgo_news_search(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "duckduckgo_news", ddg_results, ddg_error))
        for item in ddg_results:
            url = item.get("url", "").strip()
            results.append(
                SearchResult(
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
            )

        return results, diagnostics

    def _search_videos(self, plan_item: SearchPlanItem, max_results: int) -> Tuple[List[SearchResult], List[Dict[str, object]]]:
        results: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []

        youtube_results, youtube_error = self.youtube_service.search_videos(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "youtube_data_api", youtube_results, youtube_error))
        for item in youtube_results:
            snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
            identifier = item.get("id", {}) if isinstance(item.get("id"), dict) else {}
            video_id = (identifier.get("videoId") or "").strip()
            if not video_id:
                continue
            url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnails = snippet.get("thumbnails", {}) if isinstance(snippet.get("thumbnails"), dict) else {}
            media_urls = [
                thumb.get("url", "")
                for thumb in thumbnails.values()
                if isinstance(thumb, dict) and thumb.get("url")
            ]
            results.append(
                SearchResult(
                    source_type="youtube",
                    source_name=SOURCE_LABELS["youtube"],
                    platform="YouTube",
                    title=(snippet.get("title") or "").strip(),
                    url=url,
                    snippet=(snippet.get("description") or "").strip(),
                    domain="youtube.com",
                    published_at=(snippet.get("publishedAt") or "").strip(),
                    author=(snippet.get("channelTitle") or "").strip(),
                    media_urls=dedupe_urls(media_urls),
                    query_used=plan_item.query,
                    query_reason=f"{plan_item.explanation} | مزود البحث: YouTube Data API",
                    raw_payload={"search_engine": "youtube_data_api", **dict(item)},
                )
            )

        ddg_results, ddg_error = self._duckduckgo_video_search(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "duckduckgo_videos", ddg_results, ddg_error))
        for item in ddg_results:
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

            results.append(
                SearchResult(
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
            )

        return results, diagnostics

    def _search_images(self, plan_item: SearchPlanItem, max_results: int) -> Tuple[List[SearchResult], List[Dict[str, object]]]:
        results: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []

        google_results, google_error = self.google_service.search_images(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "google_images", google_results, google_error))
        for item in google_results:
            image_info = item.get("image", {}) if isinstance(item.get("image"), dict) else {}
            image_url = item.get("link", "").strip()
            source_url = image_info.get("contextLink", "").strip()
            results.append(
                SearchResult(
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
            )

        ddg_results, ddg_error = self._duckduckgo_image_search(plan_item.query, max_results=max_results)
        diagnostics.append(self._diagnostic(plan_item, "duckduckgo_images", ddg_results, ddg_error))
        for item in ddg_results:
            image_url = item.get("image", "").strip()
            source_url = item.get("url", "").strip() or image_url
            results.append(
                SearchResult(
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
            )

        return results, diagnostics

    def _make_text_results(
        self,
        *,
        plan_item: SearchPlanItem,
        items: Iterable[Dict[str, object]],
        provider_label: str,
        provider_key: str,
        href_key: str,
        title_key: str,
        snippet_key: str,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        for item in items:
            url = str(item.get(href_key, "")).strip()
            title = str(item.get(title_key, "")).strip()
            snippet = str(item.get(snippet_key, "")).strip()
            results.append(
                SearchResult(
                    source_type=plan_item.source_type,
                    source_name=SOURCE_LABELS[plan_item.source_type],
                    platform=SOURCE_LABELS[plan_item.source_type],
                    title=title,
                    url=url,
                    snippet=snippet,
                    domain=extract_domain(url),
                    query_used=plan_item.query,
                    query_reason=f"{plan_item.explanation} | مزود البحث: {provider_label}",
                    raw_payload={"search_engine": provider_key, **dict(item)},
                )
            )
        return results

    def _duckduckgo_text_search(self, query: str, max_results: int) -> Tuple[List[Dict[str, object]], str | None]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, region="wt-wt", safesearch="moderate"))
            return results, None
        except Exception as exc:
            return [], str(exc)

    def _duckduckgo_news_search(self, query: str, max_results: int) -> Tuple[List[Dict[str, object]], str | None]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.news(query, max_results=max_results, region="wt-wt", safesearch="moderate"))
            return results, None
        except Exception as exc:
            return [], str(exc)

    def _duckduckgo_video_search(self, query: str, max_results: int) -> Tuple[List[Dict[str, object]], str | None]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.videos(query, max_results=max_results, region="wt-wt", safesearch="moderate"))
            return results, None
        except Exception as exc:
            return [], str(exc)

    def _duckduckgo_image_search(self, query: str, max_results: int) -> Tuple[List[Dict[str, object]], str | None]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.images(query, max_results=max_results, safesearch="moderate"))
            return results, None
        except Exception as exc:
            return [], str(exc)

    def _duckduckgo_html_search(self, query: str, max_results: int) -> Tuple[List[Dict[str, object]], str | None]:
        try:
            response = self.session.get("https://html.duckduckgo.com/html/", params={"q": query}, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            return [], str(exc)

        soup = BeautifulSoup(response.text, "html.parser")
        items: List[Dict[str, object]] = []
        for node in soup.select(".result")[: max_results]:
            anchor = node.select_one(".result__title a, a.result__a")
            snippet_node = node.select_one(".result__snippet")
            if not anchor:
                continue
            href = self._resolve_duckduckgo_href(anchor.get("href", ""))
            items.append(
                {
                    "title": anchor.get_text(" ", strip=True),
                    "href": href,
                    "body": snippet_node.get_text(" ", strip=True) if snippet_node else "",
                }
            )
        return items, None

    def _resolve_duckduckgo_href(self, href: str) -> str:
        parsed = urlparse(href or "")
        uddg = parse_qs(parsed.query).get("uddg", [""])
        if uddg and uddg[0]:
            return unquote(uddg[0])
        return href

    def _load_direct_urls(self, urls: List[str]) -> Tuple[List[SearchResult], List[Dict[str, object]]]:
        results: List[SearchResult] = []
        diagnostics: List[Dict[str, object]] = []
        for url in dedupe_urls(urls):
            results.append(
                SearchResult(
                    source_type="direct",
                    source_name=SOURCE_LABELS["direct"],
                    platform="Direct",
                    title=f"رابط مباشر: {extract_domain(url) or url}",
                    url=url,
                    snippet="رابط مباشر أُدخل يدويًا ضمن عملية الرصد.",
                    domain=extract_domain(url),
                    query_used=url,
                    query_reason="أضيف هذا الرابط يدويًا لضمان عدم فقدان مصدر معروف مسبقًا.",
                    raw_payload={"mode": "direct", "search_engine": "manual"},
                )
            )
        diagnostics.append(
            {
                "source_type": "direct",
                "provider": "manual",
                "query": "manual input",
                "status": "ok" if results else "empty",
                "count": len(results),
                "message": "تم إدراج الروابط المباشرة التي أدخلها العضو." if results else "لا توجد روابط مباشرة مدخلة.",
            }
        )
        return results, diagnostics

    def _diagnostic(
        self,
        plan_item: SearchPlanItem,
        provider: str,
        items: List[Dict[str, object]],
        error: str | None,
    ) -> Dict[str, object]:
        if error == "not_configured":
            status = "skipped"
            message = "المزود غير مهيأ في متغيرات البيئة."
        elif error:
            status = "error"
            message = error
        elif items:
            status = "ok"
            message = f"أعاد المزود {len(items)} نتيجة أولية."
        else:
            status = "empty"
            message = "لم يعد المزود نتائج لهذا الاستعلام."

        return {
            "source_type": plan_item.source_type,
            "provider": provider,
            "query": plan_item.query,
            "strategy": plan_item.strategy,
            "status": status,
            "count": len(items),
            "message": message,
        }
