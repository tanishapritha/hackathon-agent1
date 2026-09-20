import json
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .config import DB_PATH
from .version import RESEARCH_VERSION, SCHEMA_VERSION

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_cid", "utm_reader", "fbclid", "gclid", "msclkid", "_ga", "_gi",
    "mc_cid", "mc_eid", "yclid", "ref", "ref_src"
}


def canonicalize_url(url: str) -> str:
    """Canonicalize URL by stripping tracking parameters, normalizing host & path."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        
        query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_pairs = [
            (k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS
        ]
        filtered_pairs.sort()
        query = urlencode(filtered_pairs)
        
        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return url.strip()


def normalize_query(query: str) -> str:
    """Normalize query text for deterministic caching."""
    if not query:
        return ""
    q = query.lower().strip()
    q = re.sub(r'\s+', ' ', q)
    return q


class CacheMetrics:
    def __init__(self):
        self.search_hits = 0
        self.search_misses = 0
        self.request_hits = 0
        self.request_misses = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "search_hits": self.search_hits,
            "search_misses": self.search_misses,
            "request_hits": self.request_hits,
            "request_misses": self.request_misses,
        }


metrics = CacheMetrics()


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    cache_key TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    results TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    version TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_cache (
                    cache_key TEXT PRIMARY KEY,
                    request_data TEXT NOT NULL,
                    result_data TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    version TEXT NOT NULL
                )
            """)
    finally:
        conn.close()


init_db()


def get_search_cache(
    query: str, provider: str = "tavily", max_results: int = 4, version: str = RESEARCH_VERSION
) -> Optional[List[Dict[str, Any]]]:
    norm_q = normalize_query(query)
    key = f"search:{provider}:{norm_q}:{max_results}:{version}"
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT results, expires_at FROM search_cache WHERE cache_key = ?",
            (key,)
        )
        row = cur.fetchone()
        if row:
            if time.time() < row["expires_at"]:
                metrics.search_hits += 1
                return json.loads(row["results"])
            else:
                conn.execute("DELETE FROM search_cache WHERE cache_key = ?", (key,))
                conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
        
    metrics.search_misses += 1
    return None


def set_search_cache(
    query: str,
    results: List[Dict[str, Any]],
    provider: str = "tavily",
    max_results: int = 4,
    ttl_seconds: int = 86400 * 7,
    version: str = RESEARCH_VERSION
) -> None:
    norm_q = normalize_query(query)
    key = f"search:{provider}:{norm_q}:{max_results}:{version}"
    now = time.time()
    expires_at = now + ttl_seconds
    
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache 
                (cache_key, query, provider, results, created_at, expires_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (key, norm_q, provider, json.dumps(results), now, expires_at, version)
            )
    except Exception:
        pass
    finally:
        conn.close()


def get_request_cache(
    hackathon_text: str,
    user_idea: Optional[str],
    additional_context: Optional[str],
    num_ideas: int,
    version: str = SCHEMA_VERSION
) -> Optional[Dict[str, Any]]:
    req_norm = f"{normalize_query(hackathon_text)}|{normalize_query(user_idea or '')}|{normalize_query(additional_context or '')}|{num_ideas}|{version}"
    import hashlib
    key = f"request:{hashlib.sha256(req_norm.encode()).hexdigest()}"
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT result_data, expires_at FROM request_cache WHERE cache_key = ?",
            (key,)
        )
        row = cur.fetchone()
        if row:
            if time.time() < row["expires_at"]:
                metrics.request_hits += 1
                return json.loads(row["result_data"])
            else:
                conn.execute("DELETE FROM request_cache WHERE cache_key = ?", (key,))
                conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
        
    metrics.request_misses += 1
    return None


def set_request_cache(
    hackathon_text: str,
    user_idea: Optional[str],
    additional_context: Optional[str],
    num_ideas: int,
    result_data: Dict[str, Any],
    ttl_seconds: int = 86400,
    version: str = SCHEMA_VERSION
) -> None:
    req_norm = f"{normalize_query(hackathon_text)}|{normalize_query(user_idea or '')}|{normalize_query(additional_context or '')}|{num_ideas}|{version}"
    import hashlib
    key = f"request:{hashlib.sha256(req_norm.encode()).hexdigest()}"
    now = time.time()
    expires_at = now + ttl_seconds
    
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO request_cache
                (cache_key, request_data, result_data, created_at, expires_at, version)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, req_norm, json.dumps(result_data), now, expires_at, version)
            )
    except Exception:
        pass
    finally:
        conn.close()