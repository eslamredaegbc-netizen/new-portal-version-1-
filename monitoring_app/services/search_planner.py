from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List

from monitoring_app.config import SOURCE_LABELS
from monitoring_app.models import SearchOptions, SearchPlanItem
from monitoring_app.utils.text import compact_text, dedupe_urls, normalize_text, tokenize


NEGATIVE_TERMS = [
    "شكوى",
    "استغاثة",
    "طلب مساعدة",
    "انتقاد",
    "تشهير",
    "فساد",
    "معاناة",
    "عاجل",
]

POSITIVE_TERMS = [
    "إشادة",
    "شكر",
    "نجاح",
    "إنجاز",
    "مبادرة",
    "تحسن",
]

NEUTRAL_TERMS = [
    "خبر",
    "تصريح",
    "تقرير",
    "رأي",
    "نقاش",
]


class SearchPlannerService:
    def build_plan(self, query: str, options: SearchOptions) -> Dict[str, object]:
        normalized_query = compact_text(query.strip(), 180)
        reason = compact_text(options.search_reason.strip(), 300)
        include_terms = self._dedupe_terms(options.include_terms)
        exclude_terms = self._dedupe_terms(options.exclude_terms)
        focus_terms = self._focus_terms(reason, include_terms)

        items: List[SearchPlanItem] = []
        for source in options.enabled_sources:
            items.extend(
                self._source_queries(
                    source=source,
                    query=normalized_query,
                    reason=reason,
                    include_terms=include_terms,
                    exclude_terms=exclude_terms,
                    focus_terms=focus_terms,
                    google_dork=options.google_dork,
                    official_domains=options.official_domains,
                )
            )

        criteria = {
            "topic": normalized_query,
            "reason": reason or "لم يتم تقديم سبب إضافي للبحث.",
            "included_terms": include_terms,
            "excluded_terms": exclude_terms,
            "focus_terms": focus_terms,
            "sources": [SOURCE_LABELS.get(item, item) for item in options.enabled_sources],
            "google_dork": options.google_dork.strip(),
        }
        explanation = self._build_explanation(criteria, items)
        return {
            "criteria": criteria,
            "items": items,
            "explanation": explanation,
        }

    def _source_queries(
        self,
        *,
        source: str,
        query: str,
        reason: str,
        include_terms: List[str],
        exclude_terms: List[str],
        focus_terms: List[str],
        google_dork: str,
        official_domains: List[str],
    ) -> List[SearchPlanItem]:
        items: List[SearchPlanItem] = []
        exact_phrase = f'"{query}"' if " " in query else query
        base_context = self._compose_context(query, reason, include_terms[:3], exclude_terms)
        focus_context = self._compose_context(query, " OR ".join(focus_terms[:4]), include_terms[:2], exclude_terms)

        if source in {"web", "forums", "facebook", "instagram", "official"}:
            domains: List[str]
            if source == "facebook":
                domains = ["facebook.com", "m.facebook.com"]
            elif source == "instagram":
                domains = ["instagram.com"]
            elif source == "official":
                domains = official_domains or ["gov.eg", "gov.sa", "gov.ae", "gov"]
            elif source == "forums":
                domains = []
            else:
                domains = []

            if source == "forums":
                forum_query = f'({exact_phrase}) (forum OR منتدى OR community OR discussion OR thread)'
                items.append(
                    SearchPlanItem(
                        source_type=source,
                        query=self._append_exclusions(forum_query, exclude_terms),
                        explanation="رصد النقاشات العامة والمنتديات والمجتمعات المرتبطة بالموضوع.",
                        strategy="forum-discovery",
                    )
                )
                items.append(
                    SearchPlanItem(
                        source_type=source,
                        query=self._append_exclusions(focus_context + " forum", exclude_terms),
                        explanation="توسيع البحث في المجتمعات باستخدام سبب البحث ومؤشرات المخاطر أو الإشادة.",
                        strategy="forum-context",
                    )
                )
                return items

            for domain in domains or [""]:
                domain_prefix = f"site:{domain} " if domain else ""
                items.append(
                    SearchPlanItem(
                        source_type=source,
                        query=self._append_exclusions(f"{domain_prefix}{exact_phrase} {google_dork}".strip(), exclude_terms),
                        explanation=f"استعلام مطابق مباشر داخل {SOURCE_LABELS.get(source, source)} لالتقاط النتائج الأقرب نصيًا.",
                        strategy="exact-match",
                    )
                )
                items.append(
                    SearchPlanItem(
                        source_type=source,
                        query=self._append_exclusions(f"{domain_prefix}{base_context} {google_dork}".strip(), exclude_terms),
                        explanation=f"استعلام سياقي يعتمد على سبب البحث ومصطلحات الدعم داخل {SOURCE_LABELS.get(source, source)}.",
                        strategy="context-match",
                    )
                )
                if focus_terms:
                    items.append(
                        SearchPlanItem(
                            source_type=source,
                            query=self._append_exclusions(f"{domain_prefix}{focus_context} {google_dork}".strip(), exclude_terms),
                            explanation=f"استعلام إشاري يركز على الكلمات الدالة المرتبطة بالموضوع داخل {SOURCE_LABELS.get(source, source)}.",
                            strategy="signal-match",
                        )
                    )
                if source == "facebook":
                    items.append(
                        SearchPlanItem(
                            source_type=source,
                            query=self._append_exclusions(
                                f'{domain_prefix}{exact_phrase} ("posts" OR "videos" OR "groups" OR "pages")'.strip(),
                                exclude_terms,
                            ),
                            explanation="تضييق الرصد داخل مسارات منشورات وصفحات ومجموعات Facebook العامة.",
                            strategy="facebook-surface",
                        )
                    )
                if source == "instagram":
                    items.append(
                        SearchPlanItem(
                            source_type=source,
                            query=self._append_exclusions(
                                f'{domain_prefix}{exact_phrase} ("p/" OR "reel" OR "tv")'.strip(),
                                exclude_terms,
                            ),
                            explanation="استهداف المنشورات العامة والريلز والروابط المرئية داخل Instagram.",
                            strategy="instagram-surface",
                        )
                    )
            return items

        if source == "news":
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(f"{exact_phrase} {google_dork}".strip(), exclude_terms),
                    explanation="رصد الأخبار المباشرة المرتبطة بالموضوع كما كُتبت نصيًا.",
                    strategy="news-exact",
                )
            )
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(base_context, exclude_terms),
                    explanation="توسيع الرصد الإخباري باستخدام سبب البحث والسياق التحليلي.",
                    strategy="news-context",
                )
            )
            if focus_terms:
                items.append(
                    SearchPlanItem(
                        source_type=source,
                        query=self._append_exclusions(
                            f'{exact_phrase} (news OR headline OR تصريح OR بيان OR عاجل) {" ".join(focus_terms[:3])}',
                            exclude_terms,
                        ),
                        explanation="استعلام إخباري موسع يلتقط الأخبار والتصريحات والبيانات ذات الصلة المباشرة.",
                        strategy="news-signal",
                    )
                )
            return items

        if source == "youtube":
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(f"site:youtube.com {exact_phrase}", exclude_terms),
                    explanation="التقاط الفيديوهات والقنوات التي تذكر الموضوع بصياغته المباشرة.",
                    strategy="video-exact",
                )
            )
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(f"site:youtube.com {focus_context}", exclude_terms),
                    explanation="التقاط الفيديوهات المرتبطة بسياق البحث ومؤشراته.",
                    strategy="video-context",
                )
            )
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(f'site:youtube.com "{query}" (video OR interview OR shorts OR reel)', exclude_terms),
                    explanation="توسيع البحث في YouTube ليشمل الفيديوهات والمقاطع القصيرة والمقابلات ذات الصلة.",
                    strategy="video-surface",
                )
            )
            return items

        if source == "images":
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(query, exclude_terms),
                    explanation="بحث صور مباشر لاكتشاف صور أو مواد بصرية تحمل كلمات مرتبطة بالموضوع.",
                    strategy="image-exact",
                )
            )
            items.append(
                SearchPlanItem(
                    source_type=source,
                    query=self._append_exclusions(base_context, exclude_terms),
                    explanation="بحث صور سياقي يساعد على العثور على اللافتات أو المنشورات المرئية ذات الصلة.",
                    strategy="image-context",
                )
            )
            return items

        return items

    def _focus_terms(self, reason: str, include_terms: List[str]) -> List[str]:
        normalized_reason = normalize_text(reason)
        if any(term in normalized_reason for term in ("شكوى", "انتقاد", "استغاث", "تشهير", "أزمة", "ازمه", "مخالفة", "فساد")):
            return self._dedupe_terms(include_terms + NEGATIVE_TERMS)
        if any(term in normalized_reason for term in ("مدح", "شكر", "إشادة", "نجاح", "إنجاز", "مبادرة")):
            return self._dedupe_terms(include_terms + POSITIVE_TERMS)
        return self._dedupe_terms(include_terms + NEUTRAL_TERMS + NEGATIVE_TERMS[:3])

    def _compose_context(self, query: str, reason: str, include_terms: List[str], exclude_terms: List[str]) -> str:
        parts = [query]
        if reason:
            reason_tokens = tokenize(reason)[:6]
            if reason_tokens:
                parts.append(" ".join(reason_tokens))
        if include_terms:
            parts.append(" ".join(include_terms[:4]))
        return self._append_exclusions(" ".join(part for part in parts if part), exclude_terms)

    def _append_exclusions(self, query: str, exclude_terms: List[str]) -> str:
        refined = query.strip()
        for term in exclude_terms[:5]:
            refined += f" -{term}"
        return refined.strip()

    def _dedupe_terms(self, terms: List[str]) -> List[str]:
        ordered = OrderedDict()
        for term in terms:
            cleaned = compact_text((term or "").strip(), 60)
            if cleaned:
                ordered[cleaned] = None
        return list(ordered.keys())

    def _build_explanation(self, criteria: Dict[str, object], items: List[SearchPlanItem]) -> str:
        sources = "، ".join(criteria["sources"]) if criteria.get("sources") else "غير محدد"
        include_terms = "، ".join(criteria["included_terms"]) if criteria.get("included_terms") else "لا توجد"
        exclude_terms = "، ".join(criteria["excluded_terms"]) if criteria.get("excluded_terms") else "لا توجد"
        focus_terms = "، ".join(criteria["focus_terms"]) if criteria.get("focus_terms") else "لا توجد"
        return (
            f"بُنيت خطة البحث على الموضوع '{criteria['topic']}' مع سبب البحث: {criteria['reason']}. "
            f"المصادر المستهدفة: {sources}. الكلمات الداعمة: {include_terms}. "
            f"الكلمات المستبعدة: {exclude_terms}. المؤشرات التي يُعاد استخدامها في الرصد: {focus_terms}. "
            f"تم إنشاء {len(items)} استعلامات فرعية لضمان تغطية الأخبار، المنصات الاجتماعية، المنتديات، "
            f"المواقع الرسمية، والمواد البصرية العامة."
        )
