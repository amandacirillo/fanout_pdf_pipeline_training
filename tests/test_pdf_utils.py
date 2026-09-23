from app import pdf_utils


def test_make_placeholder_pdf_page_count():
    pdf_bytes = pdf_utils.make_placeholder_pdf('Test Report', item_count=12)
    from pypdf import PdfReader
    from io import BytesIO

    reader = PdfReader(BytesIO(pdf_bytes))
    # 12 items at 5 items/page -> ceil(12/5) == 3 pages
    assert len(reader.pages) == 3


def test_merge_pdfs_combines_page_counts():
    pdf_a = pdf_utils.make_placeholder_pdf('A', item_count=3)
    pdf_b = pdf_utils.make_placeholder_pdf('B', item_count=7)
    merged = pdf_utils.merge_pdfs([pdf_a, pdf_b])

    from pypdf import PdfReader
    from io import BytesIO

    reader = PdfReader(BytesIO(merged))
    assert len(reader.pages) == 1 + 2  # ceil(3/5) + ceil(7/5)


def test_add_page_numbers_preserves_page_count():
    pdf_bytes = pdf_utils.make_placeholder_pdf('Numbered', item_count=11)
    numbered = pdf_utils.add_page_numbers(pdf_bytes)

    from pypdf import PdfReader
    from io import BytesIO

    original_pages = len(PdfReader(BytesIO(pdf_bytes)).pages)
    numbered_pages = len(PdfReader(BytesIO(numbered)).pages)
    assert original_pages == numbered_pages
