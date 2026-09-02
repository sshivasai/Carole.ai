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


def _chunk_markdown_and_docs(filename: str, text: str, max_words: int = 350, overlap_words: int = 50) -> List[tuple[str, str]]:
    """
    Splits markdown/document text along heading hierarchy (#, ##, ###) and paragraph boundaries.
    Returns a list of (section_breadcrumb, chunk_text) tuples.
    """
    import re
    lines = text.splitlines()
    chunks = []
    
    current_h1 = ""
    current_h2 = ""
    current_h3 = ""
    current_buf: List[str] = []
    
    def _flush_buffer():
        nonlocal current_buf
        if not current_buf:
            return
        
        full_section = "\n".join(current_buf).strip()
        if not full_section:
            current_buf = []
            return
            
        words = full_section.split()
        if len(words) <= max_words:
            breadcrumb = " > ".join(filter(None, [filename, current_h1, current_h2, current_h3]))
            chunks.append((breadcrumb, full_section))
        else:
            # Paragraph / Sliding sub-chunking with overlap
            i = 0
            sub_idx = 1
            while i < len(words):
                end = min(i + max_words, len(words))
                sub_text = " ".join(words[i:end])
                breadcrumb = " > ".join(filter(None, [filename, current_h1, current_h2, current_h3, f"Part {sub_idx}"]))
                chunks.append((breadcrumb, sub_text))
                sub_idx += 1
                if end == len(words):
                    break
                i += (max_words - overlap_words)
        current_buf = []

    for line in lines:
        if line.startswith("# "):
            _flush_buffer()
            current_h1 = line.lstrip("# ").strip()
            current_h2 = ""
            current_h3 = ""
        elif line.startswith("## "):
            _flush_buffer()
            current_h2 = line.lstrip("# ").strip()
            current_h3 = ""
        elif line.startswith("### "):
            _flush_buffer()
            current_h3 = line.lstrip("# ").strip()
        current_buf.append(line)

    _flush_buffer()
    return chunks if chunks else [(filename, text[:2000])]


def _chunk_code(filename: str, code: str, max_words: int = 350) -> List[tuple[str, str]]:
    """
    AST-aware chunker for Python, and structural regex chunker for JS/TS/Go/Rust/Java.
    Extracts complete class and function definitions.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    chunks = []
    
    if ext == "py":
        try:
            import ast
            tree = ast.parse(code)
            lines = code.splitlines()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start_line = node.lineno - 1
                    end_line = getattr(node, "end_lineno", len(lines))
                    block = "\n".join(lines[start_line:end_line]).strip()
                    kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                    breadcrumb = f"{filename} > {kind} `{node.name}`"
                    chunks.append((breadcrumb, block))
        except Exception:
            pass  # Fall back to structural regex

    if not chunks:
        # Generic structural / function regex split
        import re
        func_regex = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:def|class|function|const\s+\w+\s*=\s*(?:async\s*)?\(|type\s+\w+|interface\s+\w+)", re.MULTILINE)
        lines = code.splitlines()
        current_block: List[str] = []
        current_title = "Global Scope"

        for line in lines:
            if func_regex.match(line) and current_block:
                block_text = "\n".join(current_block).strip()
                if block_text:
                    chunks.append((f"{filename} > {current_title}", block_text))
                current_block = []
                current_title = line[:50].strip()
            current_block.append(line)

        if current_block:
            block_text = "\n".join(current_block).strip()
            if block_text:
                chunks.append((f"{filename} > {current_title}", block_text))

    return chunks if chunks else [(filename, code[:2000])]


def _chunk_text(filename: str, text: str) -> List[tuple[str, str]]:
    """Dispatch to code or document chunker based on file extension."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "sql", "sh"):
        return _chunk_code(filename, text)
    return _chunk_markdown_and_docs(filename, text)


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

    chunks = _chunk_text(filename, text)
    stored = 0

    for i, (breadcrumb, chunk_content) in enumerate(chunks):
        try:
            embedding = await llm_router.generate_embeddings(f"{breadcrumb}\n{chunk_content}")

            learning = Learning(
                project_id=uuid_mod.UUID(project_id),
                team_id=uuid_mod.UUID(team_id) if team_id else None,
                task_summary=breadcrumb,
                lesson_rule=chunk_content,
            )
            db.add(learning)
            await db.flush()  # Get the ID assigned

            # Also insert into LanceDB vector store
            await lancedb_client.insert_learning(
                learning_id=str(learning.id),
                project_id=project_id,
                team_id=team_id,
                task_summary=breadcrumb,
                lesson_rule=chunk_content,
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
