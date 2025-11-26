"""
Georeference API Endpoints
Dedicated endpoints for georeferencing polygons and resolving POB
"""
from fastapi import APIRouter, HTTPException, status, Body
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel
from pathlib import Path
import json

from config.paths import dossiers_state_root, dossiers_georefs_artifacts_root

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/georeference")

@router.post("/project")
async def project_polygon_to_map(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project local polygon coordinates to geographic map coordinates
    
    Args:
        request: JSON with local_coordinates, plss_anchor, starting_point, and options
    
    Returns:
        dict: Projected coordinates and metadata
    """
    try:
        logger.info("🗺️ Georeference project endpoint called")
        logger.info(f"Request keys: {list(request.keys())}")
        if request.get("plss_anchor"):
            logger.info(f"PLSS state: {request['plss_anchor'].get('state')}")
        
        # Extract request data
        local_coordinates = request.get("local_coordinates", [])
        plss_anchor = request.get("plss_anchor", {})
        starting_point = request.get("starting_point", {})
        options = request.get("options", {})
        
        if not local_coordinates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="local_coordinates are required"
            )
        
        if not plss_anchor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plss_anchor information is required"
            )
        
        # Use GeoreferenceService
        from pipelines.mapping.georeference.georeference_service import GeoreferenceService

        georeference_service = GeoreferenceService()
        result = georeference_service.georeference_polygon({
            "local_coordinates": local_coordinates,
            "plss_anchor": plss_anchor,
            "starting_point": starting_point,
            "options": options,
        })

        # Log the actual error from georeference service
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ Georeference service failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Georeference failed: {error_msg}"
            )
        
        # Log successful georeference
        if result.get("success"):
            try:
                anchor = result.get("anchor_info", {})
                coords = anchor.get("resolved_coordinates", {})
                method = result.get("projection_metadata", {}).get("method", "unknown")
                lat_val = coords.get("lat", 0.0)
                lon_val = coords.get("lon", 0.0)
                lat = float(lat_val) if lat_val is not None else 0.0
                lon = float(lon_val) if lon_val is not None else 0.0
                logger.info(f"✅ Georeference complete using {method} method at {lat:.6f}, {lon:.6f}")
            except Exception as log_err:
                logger.warning(f"Georeference succeeded but logging failed: {log_err}")

        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Georeference project endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Georeference project failed: {str(e)}"
        )

@router.post("/project-from-schema")
async def project_polygon_from_schema(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project polygon from complete schema data - handles all extraction internally
    
    Args:
        request: JSON with schema_data and polygon_data (raw from frontend)
    
    Returns:
        dict: Projected coordinates and metadata
    """
    try:
        logger.info("🗺️ Georeference project-from-schema endpoint called")
        
        schema_data = request.get("schema_data")
        polygon_data = request.get("polygon_data") 
        
        if not schema_data or not polygon_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both schema_data and polygon_data are required"
            )
        
        # Extract PLSS from first complete description
        descriptions = schema_data.get("descriptions", [])
        plss_desc = None
        for desc in descriptions:
            if desc.get("is_complete") and desc.get("plss"):
                plss_desc = desc
                break
        
        if not plss_desc:
            plss_desc = descriptions[0] if descriptions else {}
            
        plss = plss_desc.get("plss", {})
        
        # Extract local coordinates
        local_coordinates = polygon_data.get("coordinates", [])
        if not local_coordinates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No coordinates found in polygon_data"
            )
        
        # Convert coordinates to required format
        formatted_coords = []
        for coord in local_coordinates:
            if isinstance(coord, list):
                formatted_coords.append({"x": coord[0], "y": coord[1]})
            elif isinstance(coord, dict) and "x" in coord and "y" in coord:
                formatted_coords.append(coord)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid coordinate format: {coord}"
                )
        
        # Extract PLSS anchor
        plss_anchor = {
            "state": plss.get("state"),
            "township_number": plss.get("township_number"),
            "township_direction": plss.get("township_direction"),
            "range_number": plss.get("range_number"),
            "range_direction": plss.get("range_direction"),
            "section_number": plss.get("section_number"),
            "quarter_sections": plss.get("quarter_sections"),
            "principal_meridian": plss.get("principal_meridian")
        }
        
        # Extract starting point if available
        starting_point = {}
        if plss.get("starting_point", {}).get("tie_to_corner"):
            tie = plss["starting_point"]["tie_to_corner"]
            starting_point = {
                "tie_to_corner": {
                    "corner_label": tie.get("corner_label"),
                    "bearing_raw": tie.get("bearing_raw"),
                    "distance_value": tie.get("distance_value"),
                    "distance_units": tie.get("distance_units", "feet"),
                    "tie_direction": tie.get("tie_direction", "corner_bears_from_pob"),
                    "project_to_boundary": True  # Enable boundary snapping for west boundary ties
                }
            }
        
        logger.info(f"📍 Extracted PLSS anchor: {plss_anchor}")
        logger.info(f"📍 Extracted starting point: {starting_point}")
        logger.info(f"📍 Extracted {len(formatted_coords)} coordinates")
        
        # Call the existing georeference service
        from pipelines.mapping.georeference.georeference_service import GeoreferenceService
        georeference_service = GeoreferenceService()
        result = georeference_service.georeference_polygon({
            "local_coordinates": formatted_coords,
            "plss_anchor": plss_anchor,
            "starting_point": starting_point,
            "options": {
                "screen_coords_y_down": True,  # Enable Y-axis flipping for screen coordinates
                "local_units": "feet"
            }
        })
        
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ Georeference service failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Georeference failed: {error_msg}"
            )
        
        logger.info("✅ Schema-based georeference completed successfully")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Schema-based georeference endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schema-based georeference failed: {str(e)}"
        )

@router.post("/resolve-pob")
async def resolve_pob_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve Point of Beginning (POB) from PLSS anchor information
    
    Args:
        request: JSON with plss_anchor and optional tie_to_corner
    
    Returns:
        dict: POB coordinates and metadata
    """
    try:
        logger.info("📍 POB resolution endpoint called")
        
        plss_anchor = request.get("plss_anchor")
        tie_to_corner = request.get("tie_to_corner")
        
        if not plss_anchor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plss_anchor is required"
            )

        from pipelines.mapping.georeference.pob_resolver import POBResolver
        pob_resolver = POBResolver()
        result = pob_resolver.resolve_pob(plss_anchor, tie_to_corner)

        if not result.get("success"):
            error_msg = result.get("error", "POB resolution failed")
            logger.error(f"❌ POB resolution failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        
        logger.info(f"✅ POB resolved successfully using {result.get('method', 'unknown')} method")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ POB resolution endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"POB resolution failed: {str(e)}"
        )


class SaveGeorefRequest(BaseModel):
    dossier_id: str
    georef_result: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


@router.post("/save")
async def save_georeference(body: SaveGeorefRequest) -> Dict[str, Any]:
    try:
        from services.georeference.georeference_persistence_service import GeoreferencePersistenceService
        svc = GeoreferencePersistenceService()
        result = svc.save(dossier_id=body.dossier_id, georef_result=body.georef_result, metadata=body.metadata)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"💥 Failed to save georeference: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_georeferences(dossier_id: str) -> Dict[str, Any]:
    try:
        index_path = dossiers_state_root() / "georefs_index.json"
        if not index_path.exists():
            return {"status": "success", "georefs": []}
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        items = [e for e in data.get("georefs", []) if (e or {}).get("dossier_id") == str(dossier_id)]
        return {"status": "success", "georefs": items}
    except Exception as e:
        logger.error(f"💥 Error listing georeferences: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list georeferences: {str(e)}")


@router.get("/get")
async def get_georeference(dossier_id: str, georef_id: str) -> Dict[str, Any]:
    try:
        artifact_path = (
            dossiers_georefs_artifacts_root(str(dossier_id)) / f"{georef_id}.json"
        )
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Georeference artifact not found")
        with open(artifact_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {"status": "success", "artifact": payload}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Error fetching georeference: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch georeference: {str(e)}")


@router.delete("/delete")
async def delete_georeference(dossier_id: str, georef_id: str) -> Dict[str, Any]:
    try:
        from services.georeference.georeference_persistence_service import GeoreferencePersistenceService
        svc = GeoreferencePersistenceService()
        result = svc.delete_georef(dossier_id=dossier_id, georef_id=georef_id)
        if not result.get("success"):
            return {"status": "failed", **result}
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"💥 Failed to delete georeference: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkDeleteRequest(BaseModel):
    dossier_id: str
    georef_ids: List[str]


@router.post("/bulk-delete")
async def bulk_delete_georeferences(body: BulkDeleteRequest) -> Dict[str, Any]:
    try:
        from services.georeference.georeference_persistence_service import GeoreferencePersistenceService
        svc = GeoreferencePersistenceService()
        deleted: List[str] = []
        failed: List[str] = []
        for gid in body.georef_ids or []:
            try:
                res = svc.delete_georef(dossier_id=body.dossier_id, georef_id=gid)
                if res.get("success"):
                    deleted.append(gid)
                else:
                    failed.append(gid)
            except Exception:
                failed.append(gid)
        return {"status": "success", "deleted": deleted, "failed": failed}
    except Exception as e:
        logger.error(f"💥 Failed bulk delete georeferences: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list-all")
async def list_all_georeferences() -> Dict[str, Any]:
    try:
        index_path = dossiers_state_root() / "georefs_index.json"
        if not index_path.exists():
            return {"status": "success", "georefs": []}
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return {"status": "success", "georefs": data.get("georefs", [])}
    except Exception as e:
        logger.error(f"💥 Error list-all georeferences: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list georeferences: {str(e)}")
