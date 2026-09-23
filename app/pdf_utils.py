"""PDF generation and merge helpers.

Uses reportlab to build simple placeholder PDFs (standing in for whatever
real reporting library -- e.g. a plotting/graphing library -- would produce
each worker's chunk) and pypdf to merge worker outputs and stamp page numbers
onto the combined file, mirroring a common 'many small PDFs -> one numbered
PDF' post-processing step.
"""
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def make_placeholder_pdf(title: str, item_count: int) -> bytes:
    """Render a tiny multi-page PDF: one page per handful of items.

    Stands in for a worker that would normally render charts/tables for a
    slice of the requested items.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    items_per_page = 5
    pages = max(1, -(-item_count // items_per_page))  # ceil division
    for page_num in range(pages):
        c.drawString(72, 720, title)
        start = page_num * items_per_page + 1
        end = min(item_count, start + items_per_page - 1)
        c.drawString(72, 690, f'Items {start}-{end}')
        c.showPage()
    c.save()
    return buffer.getvalue()


def merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Merge multiple PDFs (in order) into a single combined PDF."""
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def add_page_numbers(pdf_bytes: bytes) -> bytes:
    """Stamp 'Page X of Y' onto the bottom-right of every page."""
    reader = PdfReader(BytesIO(pdf_bytes))
    total = len(reader.pages)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages, start=1):
        overlay_buffer = BytesIO()
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        c = canvas.Canvas(overlay_buffer, pagesize=(width, height))
        c.drawRightString(width - 36, 20, f'Page {i} of {total}')
        c.save()
        overlay_buffer.seek(0)

        overlay_page = PdfReader(overlay_buffer).pages[0]
        writer.add_page(page)
        writer.pages[-1].merge_page(overlay_page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
