from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import requests


class GoogleProgrammableSearchService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
        self.engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
        self.endpoint = "https://customsearch.googleapis.com/customsearch/v1"
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.engine_id)

    def search_text(self, query: str, max_results: int, *, language: str = "lang_ar") -> Tuple[List[Dict[str, str]], Optional[str]]:
        return self._request_items(
            query=query,
            max_results=max_results,
            extra_params={
                "lr": language,
                "safe": "active",
            },
        )

    def search_images(self, query: str, max_results: int, *, language: str = "lang_ar") -> Tuple[List[Dict[str, str]], Optional[str]]:
        return self._request_items(
            query=query,
            max_results=max_results,
            extra_params={
                "lr": language,
                "searchType": "image",
                "safe": "active",
            },
        )

    def _request_items(
        self, query: str, max_results: int, extra_params: Dict[str, str]
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        if not self.is_configured or not query.strip():
            return [], "not_configured"

        params = {
            "key": self.api_key,
            "cx": self.engine_id,
            "q": query,
            "num": max(1, min(max_results, 10)),
            **extra_params,
        }
        try:
            response = self.session.get(self.endpoint, params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return [], str(exc)

        return list(payload.get("items", []) or []), None
