
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def extract_pdf_text(pdf_source):

    try:

        if isinstance(pdf_source, bytes):
            reader = PdfReader(BytesIO(pdf_source))
            filename = "Uploaded PDF"

        else:
            file_path = Path(pdf_source)

            if file_path.suffix.lower() != ".pdf":
                raise ValueError(
                    "Invalid file type. Please provide a PDF."
                )

            reader = PdfReader(str(file_path))
            filename = file_path.name

        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:
                ok = 0
            if not ok:
                raise ValueError("The PDF is password-protected and cannot be read.")

        extracted_pages = []

        for page_number, page in enumerate(reader.pages, start=1):

            page_text = page.extract_text() or ""

            if page_text.strip():

                extracted_pages.append({
                    "page": page_number,
                    "text": page_text.strip()
                })

        full_text = "\n\n".join(
            f"--- Page {item['page']} ---\n{item['text']}"
            for item in extracted_pages
        )

        return {
            "success": bool(full_text.strip()),
            "filename": filename,
            "total_pages": len(reader.pages),
            "extracted_pages": extracted_pages,
            "full_text": full_text,
            "error": None if full_text.strip() else (
                "No readable text found. This PDF may require OCR."
            )
        }

    except Exception as error:

        return {
            "success": False,
            "filename": "PDF document",
            "total_pages": 0,
            "extracted_pages": [],
            "full_text": "",
            "error": str(error)
        }
