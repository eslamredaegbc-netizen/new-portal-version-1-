from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from monitoring_app.config import SOURCE_LABELS
from monitoring_app.models import SearchResult
from monitoring_app.utils.text import compact_text


class InsightService:
    def build_source_analysis(self, results: List[SearchResult], search_reason: str) -> Dict[str, object]:
        if not results:
            return {
                "overall_summary": "لم يتم العثور على نتائج قابلة للتحليل.",
                "source_analysis": [],
            }

        by_source: Dict[str, List[SearchResult]] = defaultdict(list)
        by_color = Counter()
        by_category = Counter()
        for result in results:
            by_source[result.source_type].append(result)
            by_color[result.color_code] += 1
            by_category[result.classification] += 1

        source_cards: List[Dict[str, object]] = []
        for source_type, items in by_source.items():
            top_item = sorted(items, key=lambda item: (item.risk_score, item.relevance_score), reverse=True)[0]
            source_cards.append(
                {
                    "source_type": source_type,
                    "source_name": SOURCE_LABELS.get(source_type, source_type),
                    "count": len(items),
                    "highest_risk": max(item.risk_score for item in items),
                    "top_category": Counter(item.classification for item in items).most_common(1)[0][0],
                    "summary": compact_text(top_item.legal_summary or top_item.snippet or top_item.title, 220),
                }
            )

        top_red = by_color.get("red", 0)
        top_yellow = by_color.get("yellow", 0)
        top_green = by_color.get("green", 0)
        dominant_category = by_category.most_common(1)[0][0] if by_category else "خبر محايد"
        top_result = sorted(results, key=lambda item: (item.risk_score, item.relevance_score), reverse=True)[0]

        overall_summary = (
            f"تحليل المصادر يشير إلى {len(results)} نتيجة مرتبطة بموضوع الرصد. "
            f"الأولوية الحالية تميل إلى التصنيف '{dominant_category}'، مع {top_red} نتائج حمراء، "
            f"{top_yellow} نتائج صفراء، و{top_green} نتائج خضراء. "
            f"أعلى نتيجة لفتًا للانتباه هي '{top_result.title}' بدرجة خطورة {top_result.risk_score}/100. "
            f"سبب البحث المدخل من العضو: {search_reason or 'غير مذكور'}."
        )
        return {
            "overall_summary": overall_summary,
            "source_analysis": sorted(source_cards, key=lambda item: item["highest_risk"], reverse=True),
        }

