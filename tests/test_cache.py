import time
import uuid
import pytest
from hackathon_intelligence.research_cache import (
    get_search_cache,
    set_search_cache,
    get_request_cache,
    set_request_cache,
    normalize_query,
)


def test_normalize_query():
    assert normalize_query("  TEST   Query   ") == "test query"
    assert normalize_query("Lower\nAND   UPPER") == "lower and upper"


def test_search_cache_hit_and_miss():
    uid = str(uuid.uuid4())
    query = f"test query for sqlite cache {uid}"
    results = [{"title": "Example", "url": "https://example.com", "snippet": "Test snippet"}]

    # Miss
    cached = get_search_cache(query, version="test_v1")
    assert cached is None

    # Set
    set_search_cache(query, results, version="test_v1")

    # Hit
    cached_hit = get_search_cache(query, version="test_v1")
    assert cached_hit == results


def test_cache_ttl_expiration():
    uid = str(uuid.uuid4())
    query = f"expiring query {uid}"
    results = [{"title": "Expired", "url": "https://example.com/expired", "snippet": "Exp"}]

    # Set with 1s TTL
    set_search_cache(query, results, ttl_seconds=1, version="test_v2")
    assert get_search_cache(query, version="test_v2") == results

    time.sleep(1.2)
    assert get_search_cache(query, version="test_v2") is None


def test_request_cache():
    uid = str(uuid.uuid4())
    text = f"Hackathon on Healthcare AI {uid}"
    user_idea = "Radiology AI assistant"
    result_data = {"ideas": [], "sources": []}

    # Miss
    assert get_request_cache(text, user_idea, None, 5, version="req_v1") is None

    # Set
    set_request_cache(text, user_idea, None, 5, result_data, version="req_v1")

    # Hit
    assert get_request_cache(text, user_idea, None, 5, version="req_v1") == result_data