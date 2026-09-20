from hackathon_intelligence.document_parser import clean_document_text


def test_clean_document_text():
    text = """
    Hello      world.

    This   is a test.
    """
    assert clean_document_text(text) == "Hello world.\nThis is a test."
