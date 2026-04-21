from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from monitoring_app.config import (
    DB_PATH,
    DEFAULT_FULL_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    EXPORTS_DIR,
)
from monitoring_app.models import CaseRecord, SearchOptions


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 390000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt, expected = stored_hash.split("$", 1)
    candidate = hash_password(password, salt).split("$", 1)[1]
    return secrets.compare_digest(candidate, expected)


class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_reason TEXT,
                    google_dork TEXT,
                    sources_json TEXT NOT NULL,
                    criteria_json TEXT,
                    plan_json TEXT,
                    overall_summary TEXT,
                    source_analysis_json TEXT,
                    created_at TEXT NOT NULL,
                    total_results INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    primary_category TEXT NOT NULL,
                    color_code TEXT DEFAULT 'yellow',
                    color_label TEXT DEFAULT 'محايد',
                    risk_score INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    summary TEXT,
                    confidence REAL NOT NULL DEFAULT 0,
                    canonical_text TEXT,
                    canonical_url TEXT,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    source_mix_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_search_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    case_id INTEGER,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    platform TEXT,
                    query_used TEXT,
                    query_reason TEXT,
                    title TEXT NOT NULL,
                    url TEXT,
                    domain TEXT,
                    snippet TEXT,
                    content_text TEXT,
                    transcript TEXT,
                    ocr_text TEXT,
                    media_urls_json TEXT,
                    published_at TEXT,
                    author TEXT,
                    classification TEXT,
                    classification_confidence REAL,
                    risk_score INTEGER,
                    relevance_score REAL,
                    color_code TEXT,
                    color_label TEXT,
                    legal_summary TEXT,
                    analyst_opinion TEXT,
                    duplicate_of INTEGER,
                    raw_json TEXT,
                    matched_signals_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(search_id) REFERENCES searches(id),
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_name TEXT NOT NULL,
                    report_title TEXT NOT NULL,
                    search_id INTEGER,
                    format TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    summary TEXT,
                    selected_results_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL,
                    result_id INTEGER NOT NULL,
                    source_type TEXT,
                    title TEXT,
                    url TEXT,
                    classification TEXT,
                    risk_score INTEGER,
                    color_code TEXT,
                    analyst_opinion TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(report_id) REFERENCES reports(id),
                    FOREIGN KEY(result_id) REFERENCES results(id)
                );
                """
            )
            self._seed_default_user(conn)
            self._migrate_legacy_columns(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate_legacy_columns(self, conn: sqlite3.Connection) -> None:
        self._ensure_columns(
            conn,
            "searches",
            {
                "search_reason": "TEXT",
                "criteria_json": "TEXT",
                "plan_json": "TEXT",
                "overall_summary": "TEXT",
                "source_analysis_json": "TEXT",
            },
        )
        self._ensure_columns(
            conn,
            "cases",
            {
                "color_code": "TEXT DEFAULT 'yellow'",
                "color_label": "TEXT DEFAULT 'محايد'",
            },
        )
        self._ensure_columns(
            conn,
            "results",
            {
                "platform": "TEXT",
                "query_used": "TEXT",
                "query_reason": "TEXT",
                "color_code": "TEXT",
                "color_label": "TEXT",
                "legal_summary": "TEXT",
                "analyst_opinion": "TEXT",
            },
        )
        self._ensure_columns(
            conn,
            "reports",
            {
                "report_title": "TEXT DEFAULT ''",
                "search_id": "INTEGER",
                "summary": "TEXT",
                "selected_results_count": "INTEGER DEFAULT 0",
                "metadata_json": "TEXT",
            },
        )
        conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection, table_name: str, columns: Dict[str, str]) -> None:
        existing_columns = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, definition in columns.items():
            if column_name not in existing_columns:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _seed_default_user(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,)).fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD), DEFAULT_FULL_NAME, "admin", utc_now()),
        )
        conn.commit()

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, full_name, role FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "role": row["role"],
        }

    def create_search(self, query: str, options: SearchOptions, plan_payload: Dict[str, Any], total_results: int) -> int:
        payload = json.dumps(
            {
                "sources": options.enabled_sources,
                "official_domains": options.official_domains,
                "direct_urls": options.direct_urls,
                "fetch_full_text": options.fetch_full_text,
                "enable_ocr": options.enable_ocr,
                "enable_video_transcript": options.enable_video_transcript,
                "search_images": options.search_images,
                "max_results_per_source": options.max_results_per_source,
                "include_terms": options.include_terms,
                "exclude_terms": options.exclude_terms,
                "language": options.language,
            },
            ensure_ascii=False,
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO searches (
                    query, search_reason, google_dork, sources_json, criteria_json,
                    plan_json, created_at, total_results
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query,
                    options.search_reason,
                    options.google_dork,
                    payload,
                    json.dumps(plan_payload.get("criteria", {}), ensure_ascii=False),
                    json.dumps(
                        [
                            {
                                "source_type": item.source_type,
                                "query": item.query,
                                "explanation": item.explanation,
                                "strategy": item.strategy,
                            }
                            for item in plan_payload.get("items", [])
                        ],
                        ensure_ascii=False,
                    ),
                    utc_now(),
                    total_results,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finalize_search(self, search_id: int, overall_summary: str, source_analysis: List[Dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE searches
                SET overall_summary = ?, source_analysis_json = ?
                WHERE id = ?
                """,
                (overall_summary, json.dumps(source_analysis, ensure_ascii=False), search_id),
            )
            conn.commit()

    def list_case_anchors(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, primary_category, canonical_text, canonical_url,
                       risk_score, confidence, evidence_count, source_mix_json
                FROM cases
                ORDER BY updated_at DESC
                """
            ).fetchall()
        anchors: List[Dict[str, Any]] = []
        for row in rows:
            anchors.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "primary_category": row["primary_category"],
                    "canonical_text": row["canonical_text"] or "",
                    "canonical_url": row["canonical_url"] or "",
                    "risk_score": row["risk_score"],
                    "confidence": row["confidence"],
                    "evidence_count": row["evidence_count"],
                    "source_mix": json.loads(row["source_mix_json"] or "{}"),
                }
            )
        return anchors

    def save_case_bundle(self, search_id: int, case: CaseRecord) -> int:
        now = utc_now()
        with self._connect() as conn:
            if case.case_id:
                current = conn.execute(
                    """
                    SELECT evidence_count, source_mix_json, risk_score, confidence
                    FROM cases
                    WHERE id = ?
                    """,
                    (case.case_id,),
                ).fetchone()
                current_mix = json.loads(current["source_mix_json"] or "{}") if current else {}
                for key, value in case.source_mix.items():
                    current_mix[key] = current_mix.get(key, 0) + value
                evidence_count = (current["evidence_count"] if current else 0) + len(case.results)
                risk_score = max(int(current["risk_score"]) if current else 0, case.risk_score)
                confidence = max(float(current["confidence"]) if current else 0.0, case.confidence)
                conn.execute(
                    """
                    UPDATE cases
                    SET title = ?, primary_category = ?, color_code = ?, color_label = ?, risk_score = ?,
                        summary = ?, confidence = ?, canonical_text = ?, canonical_url = ?, evidence_count = ?,
                        source_mix_json = ?, updated_at = ?, last_search_id = ?
                    WHERE id = ?
                    """,
                    (
                        case.title,
                        case.primary_category,
                        case.color_code,
                        case.color_label,
                        risk_score,
                        case.summary,
                        confidence,
                        case.canonical_text,
                        case.canonical_url,
                        evidence_count,
                        json.dumps(current_mix, ensure_ascii=False),
                        now,
                        search_id,
                        case.case_id,
                    ),
                )
                case_id = int(case.case_id)
            else:
                case_key = hashlib.sha1(f"{case.canonical_text}|{case.canonical_url}".encode("utf-8")).hexdigest()
                cursor = conn.execute(
                    """
                    INSERT INTO cases (
                        case_key, title, primary_category, color_code, color_label, risk_score, summary, confidence,
                        canonical_text, canonical_url, evidence_count, source_mix_json,
                        created_at, updated_at, last_search_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_key,
                        case.title,
                        case.primary_category,
                        case.color_code,
                        case.color_label,
                        case.risk_score,
                        case.summary,
                        case.confidence,
                        case.canonical_text,
                        case.canonical_url,
                        len(case.results),
                        json.dumps(case.source_mix, ensure_ascii=False),
                        now,
                        now,
                        search_id,
                    ),
                )
                case_id = int(cursor.lastrowid)

            for result in case.results:
                conn.execute(
                    """
                    INSERT INTO results (
                        search_id, case_id, source_type, source_name, platform, query_used, query_reason,
                        title, url, domain, snippet, content_text, transcript, ocr_text, media_urls_json,
                        published_at, author, classification, classification_confidence, risk_score,
                        relevance_score, color_code, color_label, legal_summary, analyst_opinion,
                        duplicate_of, raw_json, matched_signals_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        search_id,
                        case_id,
                        result.source_type,
                        result.source_name,
                        result.platform,
                        result.query_used,
                        result.query_reason,
                        result.title,
                        result.url,
                        result.domain,
                        result.snippet,
                        result.content_text,
                        result.transcript,
                        result.ocr_text,
                        json.dumps(result.media_urls, ensure_ascii=False),
                        result.published_at,
                        result.author,
                        result.classification,
                        result.classification_confidence,
                        result.risk_score,
                        result.relevance_score,
                        result.color_code,
                        result.color_label,
                        result.legal_summary,
                        result.analyst_opinion,
                        result.duplicate_of,
                        json.dumps(result.raw_payload, ensure_ascii=False),
                        json.dumps(result.matched_signals, ensure_ascii=False),
                        now,
                    ),
                )
            conn.commit()
        return case_id

    def dashboard_snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            metrics = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM cases) AS total_cases,
                    (SELECT COUNT(*) FROM results) AS total_results,
                    (SELECT COUNT(*) FROM cases WHERE risk_score >= 80) AS high_risk_cases,
                    (SELECT COUNT(*) FROM reports) AS total_reports,
                    (SELECT COUNT(*) FROM searches) AS total_searches,
                    (SELECT COUNT(*) FROM results WHERE color_code = 'red') AS red_results,
                    (SELECT COUNT(*) FROM results WHERE color_code = 'yellow') AS yellow_results,
                    (SELECT COUNT(*) FROM results WHERE color_code = 'green') AS green_results
                """
            ).fetchone()
            categories = pd.read_sql_query(
                """
                SELECT primary_category AS category, COUNT(*) AS total
                FROM cases
                GROUP BY primary_category
                ORDER BY total DESC
                """,
                conn,
            )
            sources = pd.read_sql_query(
                """
                SELECT source_type, COUNT(*) AS total
                FROM results
                GROUP BY source_type
                ORDER BY total DESC
                """,
                conn,
            )
            latest_searches = pd.read_sql_query(
                """
                SELECT id, query, search_reason, total_results, created_at
                FROM searches
                ORDER BY created_at DESC
                LIMIT 6
                """,
                conn,
            )
            recent_reports = pd.read_sql_query(
                """
                SELECT id, report_title, format, selected_results_count, created_at
                FROM reports
                ORDER BY created_at DESC
                LIMIT 5
                """,
                conn,
            )
        return {
            "metrics": dict(metrics) if metrics else {},
            "categories": categories.fillna("").to_dict(orient="records"),
            "sources": sources.fillna("").to_dict(orient="records"),
            "latest_searches": latest_searches.fillna("").to_dict(orient="records"),
            "recent_reports": recent_reports.fillna("").to_dict(orient="records"),
        }

    def get_search_bundle(self, search_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            search_row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
            if not search_row:
                return None
            results_df = pd.read_sql_query(
                """
                SELECT *
                FROM results
                WHERE search_id = ?
                ORDER BY risk_score DESC, relevance_score DESC, created_at DESC
                """,
                conn,
                params=(search_id,),
            )
            cases_df = pd.read_sql_query(
                """
                SELECT DISTINCT c.*
                FROM cases c
                INNER JOIN results r ON r.case_id = c.id
                WHERE r.search_id = ?
                ORDER BY c.risk_score DESC, c.updated_at DESC
                """,
                conn,
                params=(search_id,),
            )
        search_data = dict(search_row)
        search_data["sources"] = json.loads(search_data.get("sources_json") or "[]")
        search_data["criteria"] = json.loads(search_data.get("criteria_json") or "{}")
        search_data["plan"] = json.loads(search_data.get("plan_json") or "[]")
        search_data["source_analysis"] = json.loads(search_data.get("source_analysis_json") or "[]")
        return {
            "search": search_data,
            "results": results_df.fillna("").to_dict(orient="records"),
            "cases": cases_df.fillna("").to_dict(orient="records"),
        }

    def export_rows(self, search_id: int, selected_result_ids: List[int]) -> pd.DataFrame:
        if not selected_result_ids:
            return pd.DataFrame()
        placeholders = ",".join("?" for _ in selected_result_ids)
        query = f"""
            SELECT
                r.id AS result_id,
                r.search_id,
                c.id AS case_id,
                c.title AS case_title,
                c.primary_category,
                c.color_code AS case_color_code,
                c.risk_score AS case_risk_score,
                c.summary AS case_summary,
                r.source_type,
                r.source_name,
                r.platform,
                r.title,
                r.url,
                r.domain,
                r.query_used,
                r.query_reason,
                r.snippet,
                r.content_text,
                r.transcript,
                r.ocr_text,
                r.published_at,
                r.author,
                r.classification,
                r.classification_confidence,
                r.risk_score,
                r.relevance_score,
                r.color_code,
                r.color_label,
                r.legal_summary,
                r.analyst_opinion,
                r.created_at
            FROM results r
            LEFT JOIN cases c ON c.id = r.case_id
            WHERE r.search_id = ? AND r.id IN ({placeholders})
            ORDER BY r.risk_score DESC, r.relevance_score DESC, r.created_at DESC
        """
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=[search_id, *selected_result_ids])

    def create_report_entry(
        self,
        *,
        report_name: str,
        report_title: str,
        search_id: int,
        format_name: str,
        file_path: str,
        summary: str,
        selected_rows: Iterable[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> int:
        rows = list(selected_rows)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports (
                    report_name, report_title, search_id, format, file_path,
                    summary, selected_results_count, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_name,
                    report_title,
                    search_id,
                    format_name,
                    file_path,
                    summary,
                    len(rows),
                    json.dumps(metadata, ensure_ascii=False),
                    utc_now(),
                ),
            )
            report_id = int(cursor.lastrowid)
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO report_results (
                        report_id, result_id, source_type, title, url, classification,
                        risk_score, color_code, analyst_opinion, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        row["result_id"],
                        row.get("source_type"),
                        row.get("title"),
                        row.get("url"),
                        row.get("classification"),
                        row.get("risk_score"),
                        row.get("color_code"),
                        row.get("analyst_opinion"),
                        utc_now(),
                    ),
                )
            conn.commit()
        return report_id

    def list_reports(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, report_name, report_title, search_id, format, file_path,
                       summary, selected_results_count, metadata_json, created_at
                FROM reports
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        reports: List[Dict[str, Any]] = []
        for row in rows:
            report = dict(row)
            report["metadata"] = json.loads(report.get("metadata_json") or "{}")
            reports.append(report)
        return reports

    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                return None
            items = conn.execute(
                """
                SELECT result_id, source_type, title, url, classification, risk_score, color_code, analyst_opinion
                FROM report_results
                WHERE report_id = ?
                ORDER BY risk_score DESC, created_at DESC
                """,
                (report_id,),
            ).fetchall()
        report = dict(row)
        report["metadata"] = json.loads(report.get("metadata_json") or "{}")
        report["results"] = [dict(item) for item in items]
        return report

    def assistant_documents(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT
                    c.id AS case_id,
                    c.title AS case_title,
                    c.primary_category,
                    c.risk_score AS case_risk_score,
                    c.summary AS case_summary,
                    c.confidence AS case_confidence,
                    r.id AS result_id,
                    r.title AS result_title,
                    r.url,
                    r.snippet,
                    r.content_text,
                    r.transcript,
                    r.ocr_text,
                    r.source_type,
                    r.classification
                FROM cases c
                LEFT JOIN results r ON c.id = r.case_id
                ORDER BY c.updated_at DESC, r.risk_score DESC
                """,
                conn,
            )
