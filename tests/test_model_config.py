import os
import pytest
from hackathon_intelligence.config import DEFAULT_GEMINI_MODEL, GEMINI_MODEL


def test_default_model_is_current():
    assert DEFAULT_GEMINI_MODEL == "gemini-3.6-flash"
    assert "2.5" not in DEFAULT_GEMINI_MODEL


def test_model_environment_override():
    os.environ["GEMINI_MODEL"] = "gemini-3.6-flash"
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    assert model == "gemini-3.6-flash"