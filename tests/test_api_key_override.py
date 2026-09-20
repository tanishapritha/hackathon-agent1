import os
import json
import pytest
from hackathon_intelligence.logger import log_run, LOG_FILE, redact_secrets
from runner import resolve_api_key


def test_user_key_overrides_env_key():
    os.environ["GEMINI_API_KEY"] = "env_key_12345"
    key = resolve_api_key("user_custom_key_67890")
    assert key == "user_custom_key_67890"


def test_empty_user_key_falls_back_to_env_key():
    os.environ["GEMINI_API_KEY"] = "env_fallback_key_ABCDE"
    key1 = resolve_api_key(None)
    key2 = resolve_api_key("   ")
    assert key1 == "env_fallback_key_ABCDE"
    assert key2 == "env_fallback_key_ABCDE"


def test_missing_both_keys_raises_error():
    orig_gemini = os.environ.pop("GEMINI_API_KEY", None)
    orig_google = os.environ.pop("GOOGLE_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="No Gemini API key available"):
            resolve_api_key(None)
    finally:
        if orig_gemini:
            os.environ["GEMINI_API_KEY"] = orig_gemini
        if orig_google:
            os.environ["GOOGLE_API_KEY"] = orig_google


def test_api_keys_never_appear_in_logs():
    test_key = "AIzaSyD1234567890abcdefghijklmnopqrstuv"
    raw_error = f"Authentication failed with key {test_key}!"

    log_run(
        run_id="test_key_redaction",
        status="error",
        duration_ms=10.0,
        requested_ideas=5,
        returned_ideas=0,
        llm_calls=0,
        tool_calls=0,
        cache_hits=0,
        cache_misses=0,
        search_calls=0,
        sources_retrieved=0,
        sources_deduplicated=0,
        sources_selected=0,
        error=raw_error
    )

    assert LOG_FILE.exists()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        assert test_key not in content
        assert "[REDACTED_API_KEY]" in content


def test_redact_secrets_utility():
    secret1 = "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P"
    secret2 = "AQ.1234567890abcdefghijklmnopqrstuvwxyz1234567890"
    text = f"Errors: {secret1} and {secret2}"
    cleaned = redact_secrets(text)
    assert secret1 not in cleaned
    assert secret2 not in cleaned
    assert "[REDACTED_API_KEY]" in cleaned