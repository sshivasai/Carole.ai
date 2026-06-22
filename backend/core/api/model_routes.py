import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends
from core.auth.auth_middleware import require_auth
from core.llm.model_catalog import (
    load_model_catalog, 
    save_model_catalog, 
    reset_model_catalog
)

logger = logging.getLogger("carole.model_routes")
router = APIRouter(prefix="/api/models", tags=["Models"])

@router.get("/catalog")
async def get_catalog(user: dict = Depends(require_auth)):
    return load_model_catalog()

@router.post("/catalog")
async def update_catalog(catalog: Dict[str, Any], user: dict = Depends(require_auth)):
    save_model_catalog(catalog)
    return {"status": "ok"}

@router.post("/catalog/reset")
async def reset_catalog(user: dict = Depends(require_auth)):
    reset_model_catalog()
    return load_model_catalog()

@router.get("")
async def list_models(user: dict = Depends(require_auth)):
    return load_model_catalog()
