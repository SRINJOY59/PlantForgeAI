import base64


def to_png_b64(data: bytes, filename: str) -> list[str]:
    """Rasterise drawing files to base64 PNGs for the vision model.
    SVG never reaches here - it goes to the model as XML text."""
    name = filename.lower()
    if name.endswith((".png", ".jpg", ".jpeg")):
        return [base64.b64encode(data).decode()]
    if name.endswith(".pdf"):
        import pypdfium2 as pdfium
        pages = []
        pdf = pdfium.PdfDocument(data)
        try:
            for page in pdf:
                bitmap = page.render(scale=2.0)   # ~150dpi, tags stay legible
                png = bitmap.to_pil()
                import io
                buf = io.BytesIO()
                png.save(buf, format="PNG")
                pages.append(base64.b64encode(buf.getvalue()).decode())
        finally:
            pdf.close()
        return pages
    raise ValueError(f"cannot rasterise {filename}")
