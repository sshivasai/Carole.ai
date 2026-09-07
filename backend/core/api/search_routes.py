from fastapi import APIRouter, Depends, HTTPException, Query
import subprocess

from core.auth.auth_middleware import require_auth
from core.tools.file_tools import file_tools
from core.memory.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from core.api.crud_routes import _assert_project_access

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("/grep")
async def search_files(
    q: str = Query(..., description="The search string or pattern"),
    project_id: str | None = Query(None, description="Project ID"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    if project_id:
        await _assert_project_access(db, project_id, user["sub"])
    try:
        workspace_root = await file_tools.get_workspace_root(project_id)
        
        # We can use git grep or ripgrep if available, or just standard grep
        # Let's use `git grep` since it automatically ignores .gitignore and is fast
        # If it fails, fallback to something else or just standard grep
        
        # `-n` for line numbers, `-I` for ignoring binary files
        res = subprocess.run(
            ["git", "grep", "-n", "-I", q],
            cwd=workspace_root,
            capture_output=True,
            text=True
        )
        
        if res.returncode != 0 and res.returncode != 1:
             return {"status": "error", "message": "Search failed"}
             
        results = []
        if res.stdout:
            for line in res.stdout.split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_num = parts[1]
                    content = parts[2]
                    results.append({
                        "file": file_path,
                        "line": line_num,
                        "content": content.strip()
                    })
        
        return {"status": "success", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class CodeSearchRequest(BaseModel):
    query: str
    project_id: Optional[str] = None
    top_k: int = 10
    file_filter: Optional[str] = None
    kind: Optional[str] = None

@router.post("/code")
async def search_code(
    req: CodeSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """
    Hybrid semantic (Model2Vec) and lexical (BM25Okapi) code retrieval
    with Reciprocal Rank Fusion and cross-encoder reranking.
    """
    if req.project_id:
        await _assert_project_access(db, req.project_id, user["sub"])

    try:
        from core.knowledge.hybrid_search import hybrid_code_search
        from core.knowledge.code_graph import code_graph

        p_idx = hybrid_code_search.get_project_index(req.project_id)
        if not p_idx.file_chunks:
            chunks = await code_graph.get_all_chunks(req.project_id)
            hybrid_code_search.index_workspace_chunks(chunks, project_id=req.project_id)

        results = await hybrid_code_search.search(
            query=req.query,
            project_id=req.project_id,
            top_k=req.top_k,
            file_filter=req.file_filter,
            kind=req.kind
        )

        return {
            "status": "success",
            "query": req.query,
            "project_id": req.project_id,
            "total": len(results),
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code search error: {str(e)}")

