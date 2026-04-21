from __future__ import annotations

from collections import Counter
from typing import List

from monitoring_app.models import AssistantAnswer, AssistantEvidence
from monitoring_app.storage import DatabaseManager
from monitoring_app.utils.text import compact_text, tokenize


class InternalAssistantService:
    def __init__(self, repository: DatabaseManager) -> None:
        self.repository = repository

    def answer_question(self, question: str) -> AssistantAnswer:
        documents = self.repository.assistant_documents()
        if documents.empty:
            return AssistantAnswer(
                answer="لا توجد بيانات داخل النظام حاليًا. نفّذ عملية رصد أولًا ثم أعد السؤال.",
                confidence=0.0,
                evidence=[],
                data_scope="0 قضية / 0 سجل",
            )

        documents = documents.fillna("")
        documents["document_text"] = (
            documents["case_title"]
            + " "
            + documents["case_summary"]
            + " "
            + documents["result_title"]
            + " "
            + documents["snippet"]
            + " "
            + documents["content_text"]
            + " "
            + documents["transcript"]
            + " "
            + documents["ocr_text"]
        )
        similarities = self._score_documents(question, documents["document_text"].tolist())
        documents["similarity"] = similarities
        relevant = documents.sort_values(["similarity", "case_risk_score"], ascending=[False, False]).head(8)
        relevant = relevant[relevant["similarity"] > 0.04] if (relevant["similarity"] > 0.04).any() else relevant.head(4)

        unique_cases = relevant["case_id"].nunique()
        scope = f"{documents['case_id'].nunique()} قضية / {len(documents)} سجل"
        evidence = self._build_evidence(relevant)
        answer = self._compose_answer(question, relevant)
        avg_similarity = float(relevant["similarity"].mean()) if not relevant.empty else 0.0
        confidence = min(0.96, 0.32 + (avg_similarity * 0.55) + min(unique_cases / 10, 0.18))
        return AssistantAnswer(answer=answer, confidence=round(confidence, 2), evidence=evidence, data_scope=scope)

    def _score_documents(self, question: str, documents: List[str]):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
            matrix = vectorizer.fit_transform(documents)
            query_vector = vectorizer.transform([question.strip()])
            return cosine_similarity(query_vector, matrix).flatten()
        except Exception:
            query_tokens = set(tokenize(question))
            if not query_tokens:
                return [0.0 for _ in documents]
            scores = []
            for text in documents:
                document_tokens = set(tokenize(text))
                if not document_tokens:
                    scores.append(0.0)
                    continue
                overlap = len(query_tokens & document_tokens) / len(query_tokens)
                scores.append(overlap)
            return scores

    def _build_evidence(self, relevant) -> List[AssistantEvidence]:
        evidence: List[AssistantEvidence] = []
        seen_cases = set()
        for _, row in relevant.iterrows():
            case_id = int(row["case_id"])
            if case_id in seen_cases:
                continue
            seen_cases.add(case_id)
            snippet = row["snippet"] or row["case_summary"] or row["result_title"]
            evidence.append(
                AssistantEvidence(
                    case_id=case_id,
                    title=row["case_title"],
                    url=row["url"],
                    snippet=compact_text(snippet, 180),
                    similarity=round(float(row["similarity"]), 2),
                )
            )
            if len(evidence) >= 4:
                break
        return evidence

    def _compose_answer(self, question: str, relevant) -> str:
        if relevant.empty:
            return "لم أجد داخل النظام أدلة كافية مرتبطة بهذا السؤال."

        categories = Counter(relevant["primary_category"].tolist())
        sources = Counter(relevant["source_type"].tolist())
        top_case = relevant.sort_values(["case_risk_score", "similarity"], ascending=[False, False]).iloc[0]
        matched_cases = relevant["case_id"].nunique()
        lead = f"الإجابة مبنية فقط على {matched_cases} قضية مطابقة داخل النظام."

        normalized_question = question.replace("أ", "ا").replace("إ", "ا").lower()
        if any(term in normalized_question for term in ("كم", "عدد", "اجمالي", "إجمالي", "احص", "احصاء", "count")):
            top_categories = "، ".join(f"{name}: {count}" for name, count in categories.most_common(3))
            return (
                f"{lead} عدد القضايا الأكثر ارتباطًا بالسؤال هو {matched_cases}. "
                f"أبرز التصنيفات بين السجلات المطابقة: {top_categories or 'لا توجد تصنيفات كافية'}."
            )

        if any(term in normalized_question for term in ("اخطر", "اعلى خطوره", "الأكثر خطورة", "risk", "خطر")):
            return (
                f"{lead} أعلى قضية خطورة في النتائج المطابقة هي '{top_case['case_title']}' "
                f"بدرجة {int(top_case['case_risk_score'])}/100 وتصنيف {top_case['primary_category']}."
            )

        top_sources = "، ".join(f"{name}: {count}" for name, count in sources.most_common(3))
        top_categories = "، ".join(f"{name}: {count}" for name, count in categories.most_common(3))
        summary = compact_text(str(top_case["case_summary"] or top_case["snippet"] or top_case["result_title"]), 220)
        return (
            f"{lead} المؤشرات الأقرب تشير إلى تركّز الموضوع حول تصنيف {top_case['primary_category']} "
            f"مع أعلى خطورة مسجلة {int(top_case['case_risk_score'])}/100. "
            f"أبرز ملخص مستند: {summary}. "
            f"توزيع التصنيفات المطابقة: {top_categories or 'غير متاح'}. "
            f"وتوزيع المصادر: {top_sources or 'غير متاح'}."
        )
