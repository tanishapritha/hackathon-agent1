import fitz


def clean_document_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_text_from_pdf(path: str) -> str:
    document = fitz.open(path)
    pages = []

    try:
        for index, page in enumerate(document):
            text = page.get_text()
            if not text.strip():
                continue

            cleaned = clean_document_text(text)
            pages.append(f"[Page {index + 1}]\n{cleaned}")
    finally:
        document.close()

    result = "\n\n".join(pages)

    if not result.strip():
        raise ValueError("No readable text could be extracted from the PDF.")

    return result
