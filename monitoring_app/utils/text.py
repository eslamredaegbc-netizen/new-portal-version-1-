from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List
from urllib.parse import urlparse


ARABIC_DIACRITICS_PATTERN = re.compile(r"[\u0617-\u061A\u064B-\u0652]")
NON_WORD_PATTERN = re.compile(r"[^\w\s:/.-]+", re.UNICODE)
MULTI_SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("ـ", " ")
    value = ARABIC_DIACRITICS_PATTERN.sub("", value)
    substitutions = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }
    for source, target in substitutions.items():
        value = value.replace(source, target)
    value = NON_WORD_PATTERN.sub(" ", value.lower())
    value = MULTI_SPACE_PATTERN.sub(" ", value).strip()
    return value


def compact_text(value: str, limit: int = 260) -> str:
    value = MULTI_SPACE_PATTERN.sub(" ", (value or "").strip())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def tokenize(value: str) -> List[str]:
    normalized = normalize_text(value)
    return [token for token in normalized.split() if len(token) > 1]


def overlap_ratio(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content))
    if not content_tokens:
        return 0.0
    return len(query_tokens & content_tokens) / len(query_tokens)


def dedupe_urls(urls: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for url in urls:
        normalized = (url or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def safe_slug(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace("/", "-").replace("\\", "-")
    normalized = re.sub(r"[^a-z0-9\u0600-\u06FF -]", "", normalized)
    normalized = re.sub(r"\s+", "-", normalized).strip("-")
    return normalized or "report"


def split_lines_to_list(value: str) -> List[str]:
    if not value:
        return []
    parts = [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
    return parts
