from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import requests


class YouTubeDataSearchService:
    def __init__(self) -> None:
        self.api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        self.endpoint = "https://www.googleapis.com/youtube/v3/search"
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_videos(
        self,
        query: str,
        max_results: int,
        *,
        language: str = "ar",
        region: str = "EG",
    ) -> Tuple[List[Dict[str, object]], Optional[str]]:
        if not self.is_configured or not query.strip():
            return [], "not_configured"

        params = {
            "key": self.api_key,
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max(1, min(max_results, 10)),
            "safeSearch": "moderate",
            "relevanceLanguage": language,
            "regionCode": region,
        }
        try:
            response = self.session.get(self.endpoint, params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return [], str(exc)

        return list(payload.get("items", []) or []), None
