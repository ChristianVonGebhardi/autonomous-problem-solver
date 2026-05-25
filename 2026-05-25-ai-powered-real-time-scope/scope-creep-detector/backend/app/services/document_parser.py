import re
from typing import List
from pathlib import Path

import structlog

logger = structlog.get_logger()


def parse_pdf(file_path: str) -> str:
    """Parse PDF file and return full text."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        logger.error("pdf_parse_error", error=str(e), file_path=file_path)
        raise


def parse_docx(file_path: str) -> str:
    """Parse DOCX file and return full text."""
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        logger.error("docx_parse_error", error=str(e), file_path=file_path)
        raise


def parse_document(file_path: str, filename: str) -> str:
    """Parse document based on file extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return parse_docx(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """
    Split text into overlapping chunks for embedding.
    Tries to split on sentence/paragraph boundaries.
    """
    # Clean up text
    text = re.sub(r'\n{3,}', '\n\n', text.strip())

    # Split into sentences roughly
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk: List[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_len = len(sentence)

        if current_len + sentence_len > chunk_size and current_chunk:
            chunk = " ".join(current_chunk)
            chunks.append(chunk)

            # Keep last few sentences for overlap
            overlap_sentences: List[str] = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) < overlap:
                    overlap_sentences.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current_chunk = overlap_sentences
            current_len = sum(len(s) for s in current_chunk)

        current_chunk.append(sentence)
        current_len += sentence_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # Filter out very short chunks
    chunks = [c for c in chunks if len(c) > 50]

    return chunks


def classify_clause(text: str) -> str:
    """Simple heuristic classification of clause type."""
    text_lower = text.lower()

    scope_keywords = ["scope", "deliverable", "include", "exclude", "service", "work", "provide"]
    payment_keywords = ["payment", "invoice", "fee", "rate", "cost", "price", "billing"]
    timeline_keywords = ["deadline", "milestone", "timeline", "date", "schedule", "completion"]
    revision_keywords = ["revision", "change", "amend", "modification", "feedback"]

    scores = {
        "scope": sum(1 for k in scope_keywords if k in text_lower),
        "payment": sum(1 for k in payment_keywords if k in text_lower),
        "timeline": sum(1 for k in timeline_keywords if k in text_lower),
        "revision": sum(1 for k in revision_keywords if k in text_lower),
    }

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "general"