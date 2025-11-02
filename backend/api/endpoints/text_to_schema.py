"""
Text-to-Schema API Endpoints
Dedicated endpoints for converting text to structured parcel data
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class TextToSchemaRequest(BaseModel):
    """Request model for text-to-schema processing"""
    text: str
    parcel_id: Optional[str] = None
    model: Optional[str] = "gpt-4o"
    dossier_id: Optional[str] = None

class TextToSchemaResponse(BaseModel):
    """Response model for text-to-schema processing"""
    status: str
    structured_data: Optional[Dict[str, Any]] = None
    original_text: Optional[str] = None
    model_used: Optional[str] = None
    service_type: Optional[str] = None
    tokens_used: Optional[int] = None
    confidence_score: Optional[float] = None
    validation_warnings: Optional[list] = None
    metadata: Optional[Dict[str, Any]] = None

@router.post("/convert", response_model=TextToSchemaResponse)
async def convert_text_to_schema(request: TextToSchemaRequest):
    """
    Convert legal text to structured parcel schema
    
    Args:
        request: JSON request with text, optional parcel_id, and model selection
        
    Returns:
        TextToSchemaResponse with structured parcel data
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=400, 
                detail="Text content is required"
            )
        
        logger.info(f"📝 Converting text to schema with model: {request.model}")
        logger.info(f"📏 Text content length: {len(request.text)} characters")
        
        # Add detailed import debugging
        try:
            logger.info("🔍 Attempting to import TextToSchemaPipeline...")
            from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
            logger.info("✅ Successfully imported TextToSchemaPipeline")
            
            logger.info("🔍 Attempting to create pipeline instance...")
            pipeline = TextToSchemaPipeline()
            logger.info("✅ Successfully created pipeline instance")
            
        except Exception as import_error:
            logger.error(f"❌ Failed to import/create pipeline: {str(import_error)}")
            logger.exception("Full import traceback:")
            raise HTTPException(status_code=500, detail=f"Pipeline import failed: {str(import_error)}")
        
        # Process the text to extract structured data
        logger.info("🔍 Starting pipeline processing...")
        result = pipeline.process(request.text, request.model, request.parcel_id)
        logger.info(f"✅ Pipeline processing completed, success: {result.get('success', False)}")
        
        if not result.get("success", False):
            logger.error(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
        
        logger.info("✅ Text-to-schema conversion completed successfully!")
        return TextToSchemaResponse(
            status="success",
            structured_data=result.get("structured_data"),
            original_text=request.text,
            model_used=result.get("model_used"),
            service_type=result.get("service_type"),
            tokens_used=result.get("tokens_used"),
            confidence_score=result.get("confidence_score"),
            validation_warnings=result.get("validation_warnings", []),
            metadata={
                **(result.get("metadata") or {}),
                **({"dossier_id": request.dossier_id} if request.dossier_id else {})
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Text-to-schema conversion error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Text-to-schema conversion failed: {str(e)}")


class SaveSchemaRequest(BaseModel):
    dossier_id: str
    model_used: Optional[str] = None
    structured_data: Dict[str, Any]
    original_text: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/save")
async def save_schema_for_dossier(body: SaveSchemaRequest):
    try:
        from services.text_to_schema.schema_persistence_service import SchemaPersistenceService
        svc = SchemaPersistenceService()
        result = svc.save(body.dossier_id, body.structured_data, body.original_text, body.model_used, body.metadata)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"💥 Failed to save schema: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/schema")
async def get_parcel_schema():
    """
    Get the parcel schema template
    
    Returns:
        The current parcel schema structure
    """
    try:
        from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
        pipeline = TextToSchemaPipeline()
        
        schema = pipeline.get_schema_template()
        
        return {
            "status": "success",
            "schema": schema,
            "version": "parcel_v0.1"
        }
        
    except Exception as e:
        logger.error(f"💥 Error fetching schema: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch schema: {str(e)}")

@router.get("/models")
async def get_text_to_schema_models():
    """
    Get available models for text-to-schema processing
    
    Returns:
        Available models that support text-to-schema conversion
    """
    try:
        from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
        pipeline = TextToSchemaPipeline()
        
        models = pipeline.get_available_models()
        
        return {
            "status": "success",
            "models": models
        }
        
    except Exception as e:
        logger.error(f"💥 Error fetching models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}") 


@router.get("/list")
async def list_schemas(dossier_id: str):
    """
    List schema summaries for a dossier (from schemas_index.json)
    """
    try:
        backend_dir = Path(__file__).resolve().parents[2]
        index_path = backend_dir / "dossiers_data" / "state" / "schemas_index.json"
        if not index_path.exists():
            return {"status": "success", "schemas": []}
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        items = [e for e in data.get("schemas", []) if (e or {}).get("dossier_id") == str(dossier_id)]
        return {"status": "success", "schemas": items}
    except Exception as e:
        logger.error(f"💥 Error listing schemas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list schemas: {str(e)}")


@router.get("/get")
async def get_schema(dossier_id: str, schema_id: str):
    """
    Get a saved schema artifact by dossier_id and schema_id
    """
    try:
        backend_dir = Path(__file__).resolve().parents[2]
        artifact_path = backend_dir / "dossiers_data" / "artifacts" / "schemas" / str(dossier_id) / f"{schema_id}.json"
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Schema artifact not found")
        with open(artifact_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {"status": "success", "artifact": payload}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error fetching schema: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch schema: {str(e)}")


@router.delete("/delete")
async def delete_schema(dossier_id: str, schema_id: str, force: bool = False):
    try:
        from services.text_to_schema.schema_persistence_service import SchemaPersistenceService
        svc = SchemaPersistenceService()
        result = svc.delete_schema(dossier_id=str(dossier_id), schema_id=str(schema_id), force=force)
        # If blocked by dependents, surface conflict
        if not result.get("success") and result.get("blocked_by"):
            raise HTTPException(status_code=409, detail={"blocked_by": result.get("blocked_by")})
        return {"status": "success", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Failed to delete schema: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkSchemaDeleteRequest(BaseModel):
    items: List[Dict[str, str]]
    force: bool = False


@router.post("/bulk-delete")
async def bulk_delete_schemas(body: BulkSchemaDeleteRequest):
    try:
        from services.text_to_schema.schema_persistence_service import SchemaPersistenceService
        svc = SchemaPersistenceService()
        deleted: List[Dict[str, str]] = []
        blocked: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        for it in body.items or []:
            dossier_id = str(it.get("dossier_id"))
            schema_id = str(it.get("schema_id"))
            try:
                res = svc.delete_schema(dossier_id=dossier_id, schema_id=schema_id, force=body.force)
                if res.get("success"):
                    deleted.append(it)
                elif res.get("blocked_by"):
                    blocked.append({**it, "blocked_by": res.get("blocked_by")})
                else:
                    failed.append(it)
            except Exception:
                failed.append(it)
        return {"status": "success", "deleted": deleted, "blocked": blocked, "failed": failed}
    except Exception as e:
        logger.error(f"💥 Failed bulk delete schemas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list-all")
async def list_all_schemas():
    try:
        backend_dir = Path(__file__).resolve().parents[2]
        index_path = backend_dir / "dossiers_data" / "state" / "schemas_index.json"
        if not index_path.exists():
            return {"status": "success", "schemas": []}
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return {"status": "success", "schemas": data.get("schemas", [])}
    except Exception as e:
        logger.error(f"💥 Error list-all schemas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list schemas: {str(e)}")