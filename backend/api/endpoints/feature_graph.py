"""
Feature Graph API Endpoints
============================

Dedicated endpoints for feature graph IR artifacts (save/get/list/list-all).
These endpoints operate in parallel with legacy pipelines and provide CRUD
operations for IR, compile, judge, and bundle artifacts.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Literal
import logging

# Direct import to avoid triggering services/__init__.py
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parents[2] / "services" / "feature_graph"))
from feature_graph_persistence_service import FeatureGraphPersistenceService, ArtifactType
from feature_graph.artifacts import (
    IRArtifact,
    CompileArtifact,
    JudgeArtifact,
    BundleArtifact,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize persistence service
persistence_service = FeatureGraphPersistenceService()


class SaveArtifactRequest(BaseModel):
    """Request model for saving a feature graph artifact"""
    artifact: Dict[str, Any]
    dossier_id: str


class SaveArtifactResponse(BaseModel):
    """Response model for saving a feature graph artifact"""
    success: bool
    artifact_id: str
    path: str


class GetArtifactResponse(BaseModel):
    """Response model for getting a feature graph artifact"""
    artifact: Optional[Dict[str, Any]] = None
    found: bool


class ListArtifactsResponse(BaseModel):
    """Response model for listing feature graph artifacts"""
    artifacts: List[Dict[str, Any]]
    count: int


@router.post("/save", response_model=SaveArtifactResponse)
async def save_artifact(request: SaveArtifactRequest):
    """
    Save a feature graph artifact (IR, compile, judge, or bundle).

    Args:
        request: JSON request with artifact dict and dossier_id

    Returns:
        SaveArtifactResponse with success status, artifact_id, and path
    """
    try:
        if not request.dossier_id or not request.dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        if not request.artifact:
            raise HTTPException(
                status_code=400,
                detail="artifact is required"
            )

        # Determine artifact type and deserialize to appropriate model
        artifact_type = request.artifact.get("artifact_type")

        if artifact_type == "ir":
            artifact = IRArtifact(**request.artifact)
        elif artifact_type == "compile":
            artifact = CompileArtifact(**request.artifact)
        elif artifact_type == "judge":
            artifact = JudgeArtifact(**request.artifact)
        elif artifact_type == "bundle":
            artifact = BundleArtifact(**request.artifact)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown artifact_type: {artifact_type}. Must be one of: ir, compile, judge, bundle"
            )

        logger.info(f"💾 Saving {artifact_type} artifact {artifact.artifact_id} for dossier {request.dossier_id}")

        # Save via persistence service
        result = persistence_service.save_artifact(
            artifact=artifact,
            dossier_id=request.dossier_id
        )

        logger.info(f"✅ Successfully saved artifact {result['artifact_id']}")

        return SaveArtifactResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to save artifact: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to save artifact: {str(e)}")


@router.get("/get/{dossier_id}/{artifact_id}", response_model=GetArtifactResponse)
async def get_artifact(dossier_id: str, artifact_id: str):
    """
    Retrieve a feature graph artifact by dossier_id and artifact_id.

    Args:
        dossier_id: The dossier ID
        artifact_id: The artifact ID

    Returns:
        GetArtifactResponse with artifact dict (or None if not found)
    """
    try:
        if not dossier_id or not dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        if not artifact_id or not artifact_id.strip():
            raise HTTPException(
                status_code=400,
                detail="artifact_id is required"
            )

        logger.info(f"🔍 Retrieving artifact {artifact_id} for dossier {dossier_id}")

        artifact = persistence_service.get_artifact(
            dossier_id=dossier_id,
            artifact_id=artifact_id
        )

        if artifact:
            logger.info(f"✅ Found artifact {artifact_id}")
            return GetArtifactResponse(artifact=artifact, found=True)
        else:
            logger.info(f"❌ Artifact {artifact_id} not found")
            return GetArtifactResponse(artifact=None, found=False)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get artifact: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")


@router.get("/list/{dossier_id}", response_model=ListArtifactsResponse)
async def list_artifacts_by_dossier(
    dossier_id: str,
    artifact_type: Optional[ArtifactType] = None
):
    """
    List all artifacts for a dossier, optionally filtered by artifact_type.

    Args:
        dossier_id: The dossier ID
        artifact_type: Optional filter by artifact type (ir, compile, judge, bundle)

    Returns:
        ListArtifactsResponse with list of artifact index entries
    """
    try:
        if not dossier_id or not dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        logger.info(f"📋 Listing artifacts for dossier {dossier_id} (type filter: {artifact_type})")

        artifacts = persistence_service.list_artifacts(
            dossier_id=dossier_id,
            artifact_type=artifact_type
        )

        logger.info(f"✅ Found {len(artifacts)} artifacts")

        return ListArtifactsResponse(artifacts=artifacts, count=len(artifacts))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list artifacts: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to list artifacts: {str(e)}")


@router.get("/list-all", response_model=ListArtifactsResponse)
async def list_all_artifacts(artifact_type: Optional[ArtifactType] = None):
    """
    List all artifacts across all dossiers, optionally filtered by artifact_type.

    Args:
        artifact_type: Optional filter by artifact type (ir, compile, judge, bundle)

    Returns:
        ListArtifactsResponse with list of artifact index entries
    """
    try:
        logger.info(f"📋 Listing all artifacts (type filter: {artifact_type})")

        artifacts = persistence_service.list_artifacts(artifact_type=artifact_type)

        logger.info(f"✅ Found {len(artifacts)} artifacts")

        return ListArtifactsResponse(artifacts=artifacts, count=len(artifacts))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list all artifacts: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to list all artifacts: {str(e)}")
