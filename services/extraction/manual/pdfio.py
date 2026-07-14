def read_pdf_pages(data: bytes) -> list[str]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    try:
        pages = []
        for page in pdf:
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
        return pages
    finally:
        pdf.close()
