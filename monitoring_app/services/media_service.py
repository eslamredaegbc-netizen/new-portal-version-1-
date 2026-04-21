from __future__ import annotations

import io
from typing import Dict, List
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from monitoring_app.config import USER_AGENT
from monitoring_app.utils.text import compact_text, dedupe_urls, extract_domain


class PageMediaService:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._ocr_engine = None

    def enrich_result(
        self,
        url: str,
        *,
        fetch_full_text: bool,
        enable_ocr: bool,
        enable_video_transcript: bool,
        source_type: str,
    ) -> Dict[str, str | List[str]]:
        payload: Dict[str, str | List[str]] = {
            "content_text": "",
            "transcript": "",
            "ocr_text": "",
            "media_urls": [],
        }
        if not url:
            return payload

        domain = extract_domain(url)
        if "youtube.com" in domain or "youtu.be" in domain:
            if enable_video_transcript:
                payload["transcript"] = self.extract_youtube_transcript(url)
            return payload

        if any(host in domain for host in ("x.com", "twitter.com")):
            return payload

        if source_type == "images":
            if enable_ocr:
                payload["ocr_text"] = self.extract_image_ocr(url)
            payload["media_urls"] = [url]
            return payload

        if not fetch_full_text:
            return payload

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            return payload

        soup = BeautifulSoup(response.text, "html.parser")
        payload["content_text"] = self._extract_page_text(soup)
        media_urls = self._extract_media_urls(soup, url)
        payload["media_urls"] = media_urls
        if enable_ocr and media_urls:
            payload["ocr_text"] = self.extract_image_ocr(media_urls[0])
        return payload

    def _extract_page_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()
        text_blocks: List[str] = []
        selectors = ["article", "main", ".article", ".post", ".content", "body"]
        for selector in selectors:
            nodes = soup.select(selector)
            if not nodes:
                continue
            for node in nodes[:2]:
                for paragraph in node.find_all(["h1", "h2", "h3", "p", "li"], limit=60):
                    text = paragraph.get_text(" ", strip=True)
                    if len(text) >= 35:
                        text_blocks.append(text)
            if text_blocks:
                break
        if not text_blocks:
            text_blocks = [item.get_text(" ", strip=True) for item in soup.find_all("p", limit=40)]
        return compact_text(" ".join(text_blocks), limit=5000)

    def _extract_media_urls(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        urls: List[str] = []
        meta_image = soup.find("meta", attrs={"property": "og:image"})
        if meta_image and meta_image.get("content"):
            urls.append(urljoin(base_url, meta_image["content"]))
        for image in soup.find_all("img", limit=6):
            src = image.get("src") or image.get("data-src")
            if src:
                urls.append(urljoin(base_url, src))
        for video in soup.find_all(["video", "source"], limit=4):
            src = video.get("src")
            if src:
                urls.append(urljoin(base_url, src))
        return dedupe_urls(urls[:6])

    def extract_youtube_transcript(self, url: str) -> str:
        video_id = self._extract_youtube_video_id(url)
        if not video_id:
            return ""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["ar", "en"])
        except Exception:
            return ""
        text = " ".join(item.get("text", "") for item in transcript)
        return compact_text(text, limit=4500)

    def _extract_youtube_video_id(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc == "youtu.be":
            return parsed.path.lstrip("/")
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        path_parts = [part for part in parsed.path.split("/") if part]
        for marker in ("embed", "shorts", "live"):
            if marker in path_parts:
                marker_index = path_parts.index(marker)
                if marker_index + 1 < len(path_parts):
                    return path_parts[marker_index + 1]
        return ""

    def extract_image_ocr(self, image_url: str) -> str:
        try:
            import numpy as np
            from PIL import Image

            response = self.session.get(image_url, timeout=15)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            image_array = np.array(image)
            engine = self._load_ocr_engine()
            if not engine:
                return ""
            result, _ = engine(image_array)
            if not result:
                return ""
            extracted = " ".join(item[1] for item in result if len(item) > 1 and item[1])
            return compact_text(extracted, limit=2000)
        except Exception:
            return ""

    def _load_ocr_engine(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr_engine = RapidOCR()
        except Exception:
            self._ocr_engine = False
        return self._ocr_engine
