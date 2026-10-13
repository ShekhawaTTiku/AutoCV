"""Thread-safe PDF inspection and page rasterization via PyMuPDF."""
import math
import threading
import pymupdf

# Streamlit sessions run in different threads; serialize PDF rendering.
_pdf_lock = threading.RLock()


def page_count(pdf_bytes: bytes) -> int:
    """Return total number of pages in the given PDF bytes."""
    with _pdf_lock, pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.needs_pass or document.page_count < 1:
            raise ValueError("The PDF has no available pages.")
        return document.page_count


def render_page(pdf_bytes: bytes, page_index: int) -> bytes:
    """Render a single PDF page at optimal resolution and return PNG bytes."""
    with _pdf_lock, pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        page = document[page_index]
        width, height = page.rect.width, page.rect.height
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError("The PDF page has invalid dimensions.")
        scale = min(1200 / width, 1800 / height, 2)
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
