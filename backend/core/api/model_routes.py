from core.auth.instance_owner import require_instance_owner
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from core.auth.auth_middleware import require_auth
from core.llm.model_catalog import (
    load_model_catalog, 
    save_model_catalog, 
    reset_model_catalog
)
from core.llm.provider_sync import sync_all_provider_models

logger = logging.getLogger("carole.model_routes")
router = APIRouter(prefix="/api/models", tags=["Models"])

@router.get("/catalog")
async def get_catalog(user: dict = Depends(require_auth)):
    return load_model_catalog()

@router.post("/catalog")
async def update_catalog(catalog: Dict[str, Any], user: dict = Depends(require_instance_owner)):
    try:
        save_model_catalog(catalog)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}

@router.post("/catalog/reset")
async def reset_catalog(user: dict = Depends(require_instance_owner)):
    reset_model_catalog()
    return load_model_catalog()

@router.post("/sync")
async def sync_models(user: dict = Depends(require_instance_owner)):
    """Dynamically discover and sync latest models from active providers."""
    try:
        result = await sync_all_provider_models()
        return result
    except Exception as exc:
        logger.error("Failed to sync models: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to sync models: {exc}")

@router.get("")
async def list_models(user: dict = Depends(require_auth)):
    return load_model_catalog()

