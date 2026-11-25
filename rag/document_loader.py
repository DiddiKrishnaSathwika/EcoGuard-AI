"""Load and chunk uploaded documents."""
from pathlib import Path

from rag.text_splitter import split_text_into_chunks
from utils.pdf_reader import extract_pdf_text
from utils.validators import validate_pdf_bytes


def load_pdf_bytes(content, filename, max_mb=15):
    """Validate and extract an uploaded PDF. Never raises."""
    problem = validate_pdf_bytes(content, filename, max_mb)
    if problem:
        return {"success": False, "filename": filename, "total_pages": 0, "full_text": "", "error": problem}
    result = extract_pdf_text(content)
    result["filename"] = filename
    return result


def load_pdf_file(path, max_mb=15):
    path = Path(path)
    return load_pdf_bytes(path.read_bytes(), path.name, max_mb)


def chunk_document(text, document_id, chunk_size=1000, chunk_overlap=150):
    return [{"document_id": document_id, "chunk_index": i, "content": c}
            for i, c in enumerate(split_text_into_chunks(text, chunk_size, chunk_overlap))]
