from __future__ import annotations

from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

import requests

from monitoring_app.config import USER_AGENT


class GoogleNewsRssService:
    def __init__(self) -> None:
        self.endpoint = "https://news.google.com/rss/search"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def search_news(
        self,
        query: str,
        max_results: int,
        *,
        language: str = "ar",
        country: str = "EG",
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        if not query.strip():
            return [], "empty_query"

        params = {
            "q": query,
            "hl": language,
            "gl": country,
            "ceid": f"{country}:{language}",
        }
        try:
            response = self.session.get(self.endpoint, params=params, timeout=25)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except Exception as exc:
            return [], str(exc)

        items: List[Dict[str, str]] = []
        for item in root.findall("./channel/item")[: max_results]:
            raw_link = (item.findtext("link") or "").strip()
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "url": self._extract_target_url(raw_link) or raw_link,
                    "body": (item.findtext("description") or "").strip(),
                    "date": self._parse_date(item.findtext("pubDate") or ""),
                    "source": (item.findtext("source") or "Google News").strip(),
                }
            )
        return items, None

    def _extract_target_url(self, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value)
        uddg = parse_qs(parsed.query).get("url", [""])
        if uddg and uddg[0]:
            return unquote(uddg[0])
        return value

    def _parse_date(self, value: str) -> str:
        if not value:
            return ""
        try:
            return parsedate_to_datetime(value).isoformat()
        except Exception:
            return value
