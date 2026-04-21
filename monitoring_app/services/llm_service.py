from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

from monitoring_app.config import OPEN_SOURCE_MODEL_RECOMMENDATION


class OpenSourceLLMService:
    def __init__(self) -> None:
        self.base_url = os.getenv("OPEN_SOURCE_LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("OPEN_SOURCE_LLM_API_KEY", "")
        self.model = os.getenv("OPEN_SOURCE_LLM_MODEL", OPEN_SOURCE_MODEL_RECOMMENDATION["text_model"])

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def metadata(self) -> Dict[str, object]:
        return {
            "configured": self.is_configured,
            "model": self.model,
            "recommended_model": OPEN_SOURCE_MODEL_RECOMMENDATION,
        }

    def summarize_sources(self, prompt: str, evidence_items: List[Dict[str, str]]) -> Optional[str]:
        if not self.is_configured:
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    "أنت محلل رصد إعلامي قانوني. التزم فقط بالأدلة المقدمة، وامتنع عن الجزم بما لا تدعمه "
                    "النصوص. اكتب خلاصة مهنية قصيرة وواضحة."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    f"الأدلة:\n{self._stringify_evidence(evidence_items[:12])}"
                ),
            },
        ]
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 500,
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return None

    def _stringify_evidence(self, evidence_items: List[Dict[str, str]]) -> str:
        lines = []
        for index, item in enumerate(evidence_items, start=1):
            lines.append(
                f"{index}. العنوان: {item.get('title', '')} | "
                f"التصنيف: {item.get('classification', '')} | "
                f"الخطورة: {item.get('risk_score', '')} | "
                f"الملخص: {item.get('summary', '')} | "
                f"الرابط: {item.get('url', '')}"
            )
        return "\n".join(lines)
