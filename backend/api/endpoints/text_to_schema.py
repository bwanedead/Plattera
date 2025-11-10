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


class PurgeSchemaBody(BaseModel):
    dossier_id: str
    schema_id: str


@router.post("/purge-schema")
async def purge_schema(body: PurgeSchemaBody):
    """
    Delete a schema artifact and purge any georeferences that depend on it.
    Leaves dossier-level and unrelated data intact.
    """
    try:
        from services.text_to_schema.schema_persistence_service import SchemaPersistenceService
        svc = SchemaPersistenceService()

        backend_dir = Path(__file__).resolve().parents[2]
        georef_index = backend_dir / "dossiers_data" / "state" / "georefs_index.json"
        schemas_dir = backend_dir / "dossiers_data" / "artifacts" / "schemas" / str(body.dossier_id)

        # Resolve root id so we can purge both v1 and v2
        root_id = str(body.schema_id)
        try:
            # If looks like v2, strip suffix
            if root_id.endswith("_v2"):
                root_id = root_id[:-3]
            else:
                # Try reading artifact lineage
                art_path = schemas_dir / f"{body.schema_id}.json"
                if art_path.exists():
                    with open(art_path, "r", encoding="utf-8") as f:
                        art = json.load(f) or {}
                    rid = (art.get("lineage") or {}).get("root_schema_id")
                    if isinstance(rid, str) and rid.strip():
                        root_id = rid.strip()
        except Exception:
            pass
        ids_to_purge = {root_id, f"{root_id}_v2"}

        dependents: List[str] = []
        if georef_index.exists():
            try:
                with open(georef_index, "r", encoding="utf-8") as f:
                    idx = json.load(f) or {}
                # Discover georef artifacts referencing this schema
                for entry in idx.get("georefs", []) or []:
                    if (entry or {}).get("dossier_id") == str(body.dossier_id):
                        georef_id = (entry or {}).get("georef_id")
                        if georef_id:
                            georef_art = backend_dir / "dossiers_data" / "artifacts" / "georefs" / str(body.dossier_id) / f"{georef_id}.json"
                            if georef_art.exists():
                                try:
                                    with open(georef_art, "r", encoding="utf-8") as gf:
                                        g = json.load(gf) or {}
                                    sid = g.get("schema_id") or ((g.get("lineage") or {}).get("schema_id"))
                                    if isinstance(sid, str) and sid in ids_to_purge:
                                        # Purge this georef artifact
                                        try:
                                            georef_art.unlink()
                                            dependents.append(georef_id)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                # Rewrite georef index without purged items
                if dependents:
                    try:
                        with open(georef_index, "r", encoding="utf-8") as f:
                            idx2 = json.load(f) or {}
                        idx2["georefs"] = [
                            e for e in (idx2.get("georefs", []) or [])
                            if not ((e or {}).get("dossier_id") == str(body.dossier_id) and (e or {}).get("georef_id") in dependents)
                        ]
                        with open(georef_index, "w", encoding="utf-8") as f:
                            json.dump(idx2, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
            except Exception:
                # If index cannot be read, proceed with schema deletion only
                pass

        # Delete schema artifacts for both v1 and v2 (force semantics)
        for sid in ids_to_purge:
            try:
                _ = svc.delete_schema(dossier_id=str(body.dossier_id), schema_id=str(sid), force=True)
            except Exception:
                # Continue attempting others
                pass

        # Explicitly delete root georef <root_id>_georef if present
        try:
            georefs_dir = backend_dir / "dossiers_data" / "artifacts" / "georefs" / str(body.dossier_id)
            root_georef = georefs_dir / f"{root_id}_georef.json"
            if root_georef.exists():
                try:
                    root_georef.unlink()
                    dependents.append(f"{root_id}_georef")
                except Exception:
                    pass
            # Also remove it from georefs_index
            if georef_index.exists():
                with open(georef_index, "r", encoding="utf-8") as f:
                    idx3 = json.load(f) or {}
                idx3["georefs"] = [
                    e for e in (idx3.get("georefs", []) or [])
                    if not ((e or {}).get("dossier_id") == str(body.dossier_id) and (e or {}).get("georef_id") == f"{root_id}_georef")
                ]
                with open(georef_index, "w", encoding="utf-8") as f:
                    json.dump(idx3, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # Clear schemas latest pointer if it points to one of the purged ids
        try:
            latest_pointer = schemas_dir / "latest.json"
            if latest_pointer.exists():
                with open(latest_pointer, "r", encoding="utf-8") as f:
                    latest_obj = json.load(f) or {}
                if str(latest_obj.get("schema_id")) in ids_to_purge:
                    latest_pointer.unlink()
        except Exception:
            pass

        # Clear georefs latest pointer if it points to a purged georef
        try:
            georefs_dir = backend_dir / "dossiers_data" / "artifacts" / "georefs" / str(body.dossier_id)
            latest_georef = georefs_dir / "latest.json"
            if dependents and latest_georef.exists():
                with open(latest_georef, "r", encoding="utf-8") as f:
                    lg = json.load(f) or {}
                gid = str(lg.get("georef_id") or lg.get("id") or "")
                if gid in dependents:
                    latest_georef.unlink()
        except Exception:
            pass

        # Cleanup empty artifact directories (schemas and georefs): remove latest.json if it's the last file, then rmdir
        try:
            # Schemas directory cleanup
            remaining_schema_files = [p for p in schemas_dir.glob("*.json") if p.name != "latest.json"]
            if not remaining_schema_files:
                latest_schema = schemas_dir / "latest.json"
                if latest_schema.exists():
                    latest_schema.unlink()
                # If directory is now empty, remove it
                if schemas_dir.exists():
                    try:
                        # Only remove if truly empty
                        next(schemas_dir.iterdir())
                    except StopIteration:
                        schemas_dir.rmdir()
        except Exception:
            pass
        try:
            # Georefs directory cleanup
            georefs_dir = backend_dir / "dossiers_data" / "artifacts" / "georefs" / str(body.dossier_id)
            remaining_georef_files = [p for p in georefs_dir.glob("*.json") if p.name != "latest.json"]
            if not remaining_georef_files:
                latest_geo = georefs_dir / "latest.json"
                if latest_geo.exists():
                    latest_geo.unlink()
                if georefs_dir.exists():
                    try:
                        next(georefs_dir.iterdir())
                    except StopIteration:
                        georefs_dir.rmdir()
        except Exception:
            pass

        return {"status": "success", "purged_georefs": dependents, "purged_schema_ids": list(ids_to_purge)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Failed to purge schema: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))