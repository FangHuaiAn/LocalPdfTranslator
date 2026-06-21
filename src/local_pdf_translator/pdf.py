from __future__ import annotations

from pathlib import Path


def convert_pdf_to_markdown(pdf_path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as error:
        raise RuntimeError(
            "PDF conversion requires the optional 'markitdown' package. "
            "Install it before translating PDF files."
        ) from error

    result = MarkItDown().convert(str(pdf_path))
    text = getattr(result, "text_content", None)
    if text is None:
        text = str(result)
    return text.strip() + "\n"
