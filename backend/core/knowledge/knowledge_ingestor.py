"""
# backend/core/knowledge/knowledge_ingestor.py

Ingests uploaded files (PDF, TXT, MD) into the learnings table as vector-embedded chunks.

- Reads raw text from the file.
- Splits into chunks of ~500 words.
- Embeds each chunk via the LLM router.
- Stores as Learning rows scoped to the project.
"""

import os
import io
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import Learning
from core.llm.multi_model_router import router as llm_router


def _extract_text_from_pdf(data: bytes) -> str:
    """Extract all text from a PDF file."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def _extract_text(filename: str, data: bytes) -> str:
    """Extract text from PDF, TXT, or MD files."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return _extract_text_from_pdf(data)
    else:
        # TXT, MD, CSV, etc.
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.decode("latin-1", errors="replace")


def _chunk_text(text: str, chunk_words: int = 400) -> List[str]:
    """Split text into chunks of approximately chunk_words words."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_words):
        chunk = " ".join(words[i : i + chunk_words])
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


async def ingest_file(
    db: AsyncSession,
    project_id: str,
    team_id: str | None,
    filename: str,
    data: bytes,
) -> dict:
    """
    Main entry point: extract text, chunk it, embed each chunk, store as Learning rows.
    Returns a summary dict.
    """
    text = _extract_text(filename, data)
    if not text or len(text.strip()) < 20:
        return {"error": "Could not extract meaningful text from file.", "chunks": 0}

    chunks = _chunk_text(text)
    stored = 0

    for i, chunk in enumerate(chunks):
        try:
            embedding = await llm_router.get_embedding(chunk)
            learning = Learning(
                project_id=project_id,
                team_id=team_id,
                task_summary=f"[{filename}] — Chunk {i + 1}/{len(chunks)}",
                lesson_rule=chunk,
                embedding=embedding,
            )
            db.add(learning)
            stored += 1
        except Exception as e:
            print(f"[KnowledgeIngestor] Error embedding chunk {i}: {e}")
            continue

    await db.flush()
    return {
        "filename": filename,
        "chunks_stored": stored,
        "total_chunks": len(chunks),
        "chars": len(text),
    }
