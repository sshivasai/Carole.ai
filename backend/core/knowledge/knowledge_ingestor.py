"""
# backend/core/knowledge/knowledge_ingestor.py

Ingests uploaded files (PDF, TXT, MD) into the learnings table as vector-embedded chunks.

- Reads raw text from the file.
- Splits into chunks of ~400 words.
- Embeds each chunk via the LLM router.
- Stores as Learning rows (SQLite) + vectors (LanceDB) scoped to the project.
"""

import io
import logging
import uuid as uuid_mod
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import Learning
from core.llm.multi_model_router import llm_router  # ← fixed: was `router`
from core.memory.lancedb_client import lancedb_client

logger = logging.getLogger("carole.knowledge")


def _extract_text_from_pdf(data: bytes) -> str:
    """Extract all text from a PDF file using PyPDF2."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except ImportError:
        return "[PDF extraction error: PyPDF2 not installed. Run: pip install PyPDF2]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def _extract_text(filename: str, data: bytes) -> str:
    """Extract text from PDF, TXT, MD, CSV, or any plain-text file."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return _extract_text_from_pdf(data)
    # TXT, MD, CSV, JSON, YAML, etc.
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
    Main entry point: extract text, chunk it, embed each chunk,
    and store as Learning rows in both SQLite and LanceDB.
    Returns a summary dict.
    """
    text = _extract_text(filename, data)
    if not text or len(text.strip()) < 20:
        return {"error": "Could not extract meaningful text from file.", "chunks": 0}

    chunks = _chunk_text(text)
    stored = 0

    for i, chunk in enumerate(chunks):
        try:
            embedding = await llm_router.generate_embeddings(chunk)

            learning = Learning(
                project_id=uuid_mod.UUID(project_id),
                team_id=uuid_mod.UUID(team_id) if team_id else None,
                task_summary=f"[{filename}] — Chunk {i + 1}/{len(chunks)}",
                lesson_rule=chunk,
            )
            db.add(learning)
            await db.flush()  # Get the ID assigned

            # Also insert into LanceDB vector store
            await lancedb_client.insert_learning(
                learning_id=str(learning.id),
                project_id=project_id,
                team_id=team_id,
                task_summary=learning.task_summary,
                lesson_rule=chunk,
                vector=embedding,
            )
            stored += 1
        except Exception as e:
            logger.error("[KnowledgeIngestor] Error embedding chunk %d of '%s': %s", i, filename, e)
            continue

    await db.commit()

    return {
        "filename": filename,
        "chunks_stored": stored,
        "total_chunks": len(chunks),
        "chars": len(text),
    }
