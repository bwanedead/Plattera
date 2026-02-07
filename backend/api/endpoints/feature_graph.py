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
from feature_graph.models import FeatureGraph
from feature_graph.compiler import compile_graph
from feature_graph.judge import judge_graph
from feature_graph.bundle import bundle_feature_graph
from feature_graph.artifacts import create_compile_artifact, create_judge_artifact

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


# ============================================================================
# COMPILE / JUDGE / BUNDLE ENDPOINTS
# ============================================================================

class CompileRequest(BaseModel):
    """Request model for compiling a feature graph"""
    graph: Dict[str, Any]
    dossier_id: str
    artifact_id: Optional[str] = None
    parent_artifact_ids: Optional[List[str]] = None


class CompileResponse(BaseModel):
    """Response model for compile operation"""
    success: bool
    artifact: Dict[str, Any]
    artifact_id: str


class JudgeRequest(BaseModel):
    """Request model for judging a feature graph"""
    graph: Dict[str, Any]
    dossier_id: str
    artifact_id: Optional[str] = None
    parent_artifact_ids: Optional[List[str]] = None
    include_warnings: bool = True


class JudgeResponse(BaseModel):
    """Response model for judge operation"""
    success: bool
    artifact: Dict[str, Any]
    artifact_id: str


class BundleRequest(BaseModel):
    """Request model for bundling a feature graph"""
    target_graph: Dict[str, Any]
    available_graphs: Optional[Dict[str, Dict[str, Any]]] = None
    dossier_id: str
    artifact_id: Optional[str] = None
    parent_artifact_ids: Optional[List[str]] = None
    created_by: Optional[str] = None
    bundle_purpose: Optional[str] = None


class BundleResponse(BaseModel):
    """Response model for bundle operation"""
    success: bool
    artifact: Dict[str, Any]
    artifact_id: str


@router.post("/compile", response_model=CompileResponse)
async def compile_feature_graph(request: CompileRequest):
    """
    Compile a feature graph into concrete geometry outputs.

    This endpoint runs best-effort compilation: produces partial results with
    typed gaps for unsupported operations or missing parameters.

    Args:
        request: CompileRequest with graph dict and dossier_id

    Returns:
        CompileResponse with CompileArtifact containing compiled features and gaps
    """
    try:
        if not request.dossier_id or not request.dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        if not request.graph:
            raise HTTPException(
                status_code=400,
                detail="graph is required"
            )

        logger.info(f"🔧 Compiling feature graph for dossier {request.dossier_id}")

        # Deserialize graph
        graph = FeatureGraph(**request.graph)

        # Run compiler
        compile_result = compile_graph(graph)

        # Create compile artifact
        artifact_id = request.artifact_id or f"compile_{graph.graph_id}"
        parent_ids = request.parent_artifact_ids or [graph.graph_id]

        compile_artifact = create_compile_artifact(
            artifact_id=artifact_id,
            source_graph=graph,
            compiled_features=compile_result.compiled_features,
            gaps=compile_result.gaps,
            warnings=compile_result.warnings,
            parent_artifact_ids=parent_ids
        )

        # Save artifact
        result = persistence_service.save_artifact(
            artifact=compile_artifact,
            dossier_id=request.dossier_id
        )

        logger.info(f"✅ Compiled graph with {len(compile_result.compiled_features)} features, {len(compile_result.gaps)} gaps")

        return CompileResponse(
            success=True,
            artifact=compile_artifact.dict(),
            artifact_id=result["artifact_id"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to compile graph: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to compile graph: {str(e)}")


@router.post("/judge", response_model=JudgeResponse)
async def judge_feature_graph(request: JudgeRequest):
    """
    Validate a feature graph and produce typed gap records.

    The judge performs deterministic validation:
    - Missing anchors (features without global frame references)
    - Missing operands (operations referencing non-existent features)
    - Missing parameters (operations with missing required params)
    - Unsupported operations (operations not yet implemented)

    Args:
        request: JudgeRequest with graph dict and dossier_id

    Returns:
        JudgeResponse with JudgeArtifact containing judge report and gaps
    """
    try:
        if not request.dossier_id or not request.dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        if not request.graph:
            raise HTTPException(
                status_code=400,
                detail="graph is required"
            )

        logger.info(f"⚖️ Judging feature graph for dossier {request.dossier_id}")

        # Deserialize graph
        graph = FeatureGraph(**request.graph)

        # Run judge
        judge_report = judge_graph(graph, include_warnings=request.include_warnings)

        # Create judge artifact
        artifact_id = request.artifact_id or f"judge_{graph.graph_id}"
        parent_ids = request.parent_artifact_ids or [graph.graph_id]

        judge_artifact = create_judge_artifact(
            artifact_id=artifact_id,
            source_graph=graph,
            judge_report=judge_report,
            parent_artifact_ids=parent_ids
        )

        # Save artifact
        result = persistence_service.save_artifact(
            artifact=judge_artifact,
            dossier_id=request.dossier_id
        )

        logger.info(f"✅ Judge report: {judge_report.status}, {len(judge_report.gaps)} gaps")

        return JudgeResponse(
            success=True,
            artifact=judge_artifact.dict(),
            artifact_id=result["artifact_id"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to judge graph: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to judge graph: {str(e)}")


@router.post("/bundle", response_model=BundleResponse)
async def bundle_graph(request: BundleRequest):
    """
    Bundle a feature graph with its minimal dependency subgraph.

    The bundler performs recursive dependency discovery and packages
    the target graph with all referenced graphs, recording why each
    dependency was included.

    Args:
        request: BundleRequest with target_graph, available_graphs, and dossier_id

    Returns:
        BundleResponse with BundleArtifact containing target + dependencies
    """
    try:
        if not request.dossier_id or not request.dossier_id.strip():
            raise HTTPException(
                status_code=400,
                detail="dossier_id is required"
            )

        if not request.target_graph:
            raise HTTPException(
                status_code=400,
                detail="target_graph is required"
            )

        logger.info(f"📦 Bundling feature graph for dossier {request.dossier_id}")

        # Deserialize target graph
        target_graph = FeatureGraph(**request.target_graph)

        # Deserialize available graphs if provided
        available_graphs = None
        if request.available_graphs:
            available_graphs = {
                graph_id: FeatureGraph(**graph_dict)
                for graph_id, graph_dict in request.available_graphs.items()
            }

        # Run bundler
        artifact_id = request.artifact_id or f"bundle_{target_graph.graph_id}"
        bundle_artifact = bundle_feature_graph(
            target_graph=target_graph,
            available_graphs=available_graphs,
            bundle_id=artifact_id,
            created_by=request.created_by,
            bundle_purpose=request.bundle_purpose
        )

        # Override parent_artifact_ids if provided
        if request.parent_artifact_ids:
            bundle_artifact.parent_artifact_ids = request.parent_artifact_ids

        # Save artifact
        result = persistence_service.save_artifact(
            artifact=bundle_artifact,
            dossier_id=request.dossier_id
        )

        logger.info(f"✅ Bundled graph with {len(bundle_artifact.dependency_graphs)} dependencies")

        return BundleResponse(
            success=True,
            artifact=bundle_artifact.dict(),
            artifact_id=result["artifact_id"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to bundle graph: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to bundle graph: {str(e)}")
