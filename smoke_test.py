"""Local smoke test for the deterministic portions of the project."""
from hackathon_intelligence.document_parser import clean_document_text
from hackathon_intelligence.research_cache import make_key, set, get


def main():
    assert clean_document_text("  hello   world  ") == "hello world"
    key = make_key("smoke", "hello")
    set("web", key, {"ok": True}, ttl=60)
    assert get("web", key) == {"ok": True}
    print("Deterministic smoke test passed.")


if __name__ == "__main__":
    main()
