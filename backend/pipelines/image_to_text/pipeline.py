"""
Image to Text Processing Pipeline
=================================

🎯 CLEAN ARCHITECTURE - PURE ORCHESTRATION LAYER 🎯
==================================================

This module is the central orchestrator for image-to-text processing.
It maintains clean separation of concerns by delegating specialized logic to dedicated modules.

CURRENT ARCHITECTURE:
====================
📁 pipeline.py           → Core orchestration (this file)
📁 redundancy.py          → Parallel execution & consensus logic  
📁 utils/text_utils.py    → Reusable text processing utilities
📁 alignment/             → Validation, tokenization & alignment algorithms
📁 image_processor.py     → Image enhancement & preparation

ORCHESTRATION DATA FLOWS:
=========================

SINGLE PROCESSING:
API → pipeline.process() → service → _standardize_response() → Frontend

REDUNDANCY PROCESSING:  
API → pipeline.process_with_redundancy() → RedundancyProcessor.process() → Frontend

CRITICAL INTEGRATION POINTS:
============================

SERVICE INTERFACE:
- service.process_image_with_text(image_data, prompt, model, image_format, json_mode)
- MUST return: {"success": bool, "extracted_text": str, "tokens_used": int, ...}

IMAGE PROCESSING:
- enhance_for_character_recognition(image_path) → (base64_string, format_string)
- Pipeline handles image preparation and base64 encoding

RESPONSE FORMAT (UNCHANGED):
{
    "success": True,
    "extracted_text": "...",  # Frontend dependency
    "model_used": "gpt-4o", 
    "service_type": "llm",
    "tokens_used": 6561,
    "confidence_score": 1.0,
    "metadata": {...}
}

REDUNDANCY INTEGRATION:
======================
- RedundancyProcessor handles: parallel execution, consensus analysis, response formatting
- Pipeline orchestrates: service routing, image preparation, delegation to processor
- Maintains same response format for frontend compatibility

SAFETY RULES:
============
✅ SAFE TO MODIFY:
- Internal orchestration logic
- Error handling improvements  
- Additional metadata fields
- Service routing enhancements

❌ DO NOT MODIFY:
- Public method signatures (process, process_with_redundancy)
- Response format structure (breaks frontend)
- Service interface calls (breaks integrations)
- Image preparation return types (breaks image processing)

DEFAULT MODES:
=============
- Default extraction_mode: "legal_document_json_relaxed" (structured output, local validation/repair)
- Default model: "gpt-4o" (balanced speed/quality)
- JSON mode auto-enables redundancy for better consensus analysis
"""
from services.registry import get_registry
from prompts.image_to_text import get_image_to_text_prompt
import base64
import hashlib
import os
import threading
import time
from pathlib import Path
import logging
from typing import Tuple, Dict, Any, Optional, Union
import json
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
from pipelines.image_to_text.image_processor import enhance_for_character_recognition
from pipelines.image_to_text.redundancy import RedundancyProcessor
from agent_kernel.session import KernelSessionManager
from agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanOpenerTool,
)
from agents.transcript_edit.controller import run_transcript_edit_controller_loop
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService
from transcript_edit.contracts import (
    EditLoopStartRequestV0,
    TranscriptionEditRunRequestV0,
)
from transcript_edit.persistence import TranscriptionEditPersistenceService
from transcript_edit.run_registry import TranscriptionEditRunRegistry
from config.paths import dossiers_root
from transcript_edit.run_service import TranscriptionEditRunService

logger = logging.getLogger(__name__)

_LEGAL_JSON_MODES = {"legal_document_json", "legal_document_json_relaxed"}
_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"


def _extract_best_result_index(metadata: Any) -> int | None:
    if not isinstance(metadata, dict):
        return None
    analysis = metadata.get("redundancy_analysis")
    if not isinstance(analysis, dict):
        return None
    value = analysis.get("best_result_index")
    return value if isinstance(value, int) and value >= 0 else None


class _LegalSectionV0(BaseModel):
    id: int = Field(..., ge=1)
    body: str


class _LegalDocumentV0(BaseModel):
    documentId: str = Field(..., min_length=1)
    sections: list[_LegalSectionV0] = Field(..., min_length=1)

class ImageToTextPipeline:
    """
    Clean, decoupled pipeline for image-to-text processing
    
    🔴 CRITICAL ORCHESTRATOR - MAINTAINS SERVICE INTEGRATION 🔴
    """
    
    def __init__(self):
        # CRITICAL: Registry provides service routing
        self.registry = get_registry()
        # Initialize redundancy processor
        self.redundancy_processor = RedundancyProcessor()
        self.transcription_edit_run_service = TranscriptionEditRunService()
        self.transcription_edit_persistence = TranscriptionEditPersistenceService()
        self.transcription_edit_run_registry = TranscriptionEditRunRegistry()
    
    def process(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document_json_relaxed", enhancement_settings: dict = None) -> dict:
        """
        Process an image to extract text
        
        🔴 CRITICAL ENTRY POINT - DO NOT MODIFY SIGNATURE 🔴
        
        Args:
            image_path: Path to the image file
            model: Model identifier to use for processing
            extraction_mode: Mode of extraction (legal_document, simple_ocr, etc.)
            enhancement_settings: Optional dict with contrast, sharpness, brightness, color values
            
        Returns:
            dict: Processing result with extracted text and metadata
            
        CRITICAL FLOW:
        1. Get service for model (OpenAI for gpt-4o, gpt-o4-mini)
        2. Prepare enhanced image (base64 encoding)
        3. Get appropriate prompt for extraction mode
        4. Call service.process_image_with_text()
        5. Standardize response format
        """
        try:
            extraction_mode = self._effective_extraction_mode(extraction_mode)
            # CRITICAL: Get the appropriate service for this model
            # This routing is essential for multi-service support
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            # CRITICAL: Prepare the enhanced image
            # This MUST return (base64_string, format_string) tuple
            image_data, image_format = self._prepare_image(image_path, enhancement_settings)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }
            
            # CRITICAL: Get the prompt for this extraction mode and model
            # Different models may need different prompts
            prompt = get_image_to_text_prompt(extraction_mode, model)
            # Append optional user instruction if present
            try:
                ui = (enhancement_settings or {}).get('user_instruction')
                if ui:
                    prompt = f"{prompt}\n\nUser instruction:\n{ui}\n"
                    logger.info(f"🧩 Appended user instruction ({len(ui)} chars)")
            except Exception:
                pass
            
            # CRITICAL: Process based on service type
            # OpenAI service MUST have process_image_with_text method
            if hasattr(service, 'process_image_with_text'):
                # LLM service (OpenAI)
                # Pass JSON mode flag for structured response
                json_mode = self._json_mode_kind(extraction_mode)
                result = service.process_image_with_text(
                    image_data=image_data,    # CRITICAL: base64 string
                    prompt=prompt,
                    model=model,
                    image_format=image_format,  # CRITICAL: format string
                    json_mode=json_mode  # CRITICAL: Enable structured JSON response
                )
            elif hasattr(service, 'extract_text'):
                # OCR service
                result = service.extract_text(image_path, model)
            else:
                return {
                    "success": False,
                    "error": f"Service {service.__class__.__name__} doesn't support image processing"
                }

            result = self._postprocess_legal_json_result(
                result=result,
                extraction_mode=extraction_mode,
                model=model,
                context={"pipeline_method": "process"},
            )
            
            # CRITICAL: Standardize the response
            # This ensures consistent format for frontend
            return self._standardize_response(result, model, service)
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _get_service_for_model(self, model: str):
        """
        Find the appropriate service for a given model
        
        🔴 CRITICAL SERVICE ROUTING - MAINTAINS MODEL-SERVICE MAPPING 🔴
        """
        # CRITICAL: Get all available models from registry
        all_models = self.registry.get_all_models()
        
        if model not in all_models:
            return None
            
        # CRITICAL: Extract service routing information
        model_info = all_models[model]
        service_type = model_info.get("service_type")
        service_name = model_info.get("service_name")
        
        # CRITICAL: Route to appropriate service type
        if service_type == "llm":
            return self.registry.llm_services.get(service_name)
        elif service_type == "ocr":
            return self.registry.ocr_services.get(service_name)
        
        return None

    def _json_mode_kind(self, extraction_mode: str) -> Union[str, bool]:
        if extraction_mode == "legal_document_json":
            return "strict"
        if extraction_mode == "legal_document_json_relaxed":
            return "relaxed"
        return False

    def _effective_extraction_mode(self, extraction_mode: str) -> str:
        force_strict = str(os.getenv("PLATTERA_IMAGE_TO_TEXT_FORCE_STRICT_JSON", "")).strip().lower()
        if force_strict in {"1", "true", "yes", "on"} and extraction_mode == "legal_document_json_relaxed":
            logger.warning("⚠️ Internal override enabled: forcing strict JSON extraction mode")
            return "legal_document_json"
        return extraction_mode

    def _is_relaxed_legal_json_mode(self, extraction_mode: str) -> bool:
        return extraction_mode == "legal_document_json_relaxed"

    def _postprocess_legal_json_result(
        self,
        *,
        result: dict,
        extraction_mode: str,
        model: str,
        context: dict[str, Any] | None = None,
    ) -> dict:
        if extraction_mode not in _LEGAL_JSON_MODES:
            return result
        if not result.get("success", False):
            return result

        context = context or {}
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        extracted_text = result.get("extracted_text")
        if not isinstance(extracted_text, str) or not extracted_text.strip():
            return result

        validated = self._validate_legal_document_json_payload(extracted_text)
        validation_passed = bool(validated is not None)
        repair_invoked = False
        repair_snapshot_ref = None
        raw_output_ref = None

        if validation_passed:
            normalized_payload = validated
        elif self._is_relaxed_legal_json_mode(extraction_mode):
            repair_invoked = True
            raw_output_ref = self._persist_relaxed_raw_output_for_postmortem(
                raw_output=extracted_text,
                model=model,
                context=context,
            )
            normalized_payload, repair_snapshot_ref = self._repair_relaxed_json_with_edit_loop(
                raw_output=extracted_text,
                context=context,
            )
        else:
            normalized_payload = None

        if isinstance(normalized_payload, dict):
            result["extracted_text"] = json.dumps(normalized_payload, ensure_ascii=False)
        elif self._is_relaxed_legal_json_mode(extraction_mode):
            result["success"] = False
            result["error"] = "relaxed_json_validation_and_repair_failed"
            metadata.setdefault("json_extraction", {})
            metadata["json_extraction"].update(
                {
                    "mode": self._json_mode_kind(extraction_mode),
                    "validation_passed": validation_passed,
                    "repair_invoked": repair_invoked,
                    "repair_snapshot_ref": repair_snapshot_ref,
                    "raw_output_ref": raw_output_ref,
                }
            )
            self._persist_json_extraction_metric(
                extraction_mode=extraction_mode,
                model=model,
                validation_passed=validation_passed,
                repair_invoked=repair_invoked,
                recovered=False,
                repair_snapshot_ref=repair_snapshot_ref,
                raw_output_ref=raw_output_ref,
                context=context,
            )
            result["metadata"] = metadata
            return result

        metadata.setdefault("json_extraction", {})
        metadata["json_extraction"].update(
            {
                "mode": self._json_mode_kind(extraction_mode),
                "validation_passed": validation_passed,
                "repair_invoked": repair_invoked,
                "repair_snapshot_ref": repair_snapshot_ref,
                "raw_output_ref": raw_output_ref,
            }
        )
        self._persist_json_extraction_metric(
            extraction_mode=extraction_mode,
            model=model,
            validation_passed=validation_passed,
            repair_invoked=repair_invoked,
            recovered=isinstance(normalized_payload, dict),
            repair_snapshot_ref=repair_snapshot_ref,
            raw_output_ref=raw_output_ref,
            context=context,
        )
        self._maybe_trigger_transcript_edit_agent_background(
            extraction_mode=extraction_mode,
            normalized_payload=normalized_payload if isinstance(normalized_payload, dict) else None,
            context={
                **context,
                "best_result_index": _extract_best_result_index(metadata),
            },
        )
        result["metadata"] = metadata
        logger.info(
            "json_extraction_outcome %s",
            json.dumps(
                {
                    "mode": metadata["json_extraction"].get("mode"),
                    "model": model,
                    "validation_passed": validation_passed,
                    "repair_invoked": repair_invoked,
                    "repair_snapshot_ref": repair_snapshot_ref,
                    "raw_output_ref": raw_output_ref,
                    "tokens_used": result.get("tokens_used"),
                    "finish_reason": metadata.get("finish_reason"),
                },
                ensure_ascii=False,
            ),
        )
        return result

    def _maybe_trigger_transcript_edit_agent_background(
        self,
        *,
        extraction_mode: str,
        normalized_payload: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> None:
        if extraction_mode != "legal_document_json_relaxed":
            return
        if not isinstance(normalized_payload, dict):
            return
        policy_mode = self._post_t0_tx_agent_mode()
        if policy_mode == _MODE_OFF:
            return
        execution_mode = self._post_t0_tx_agent_execution()
        dossier_id = context.get("dossier_id")
        if not isinstance(dossier_id, str) or not dossier_id.strip():
            return
        transcription_id = str(context.get("transcription_id") or "").strip() or None
        best_result_index_raw = context.get("best_result_index")
        best_result_index = best_result_index_raw if isinstance(best_result_index_raw, int) else None
        source_transcript_ref = self._resolve_post_t0_source_transcript_ref(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            best_result_index=best_result_index,
        )
        source_text = None
        input_kind = "ref" if source_transcript_ref else "text"
        if source_transcript_ref is None:
            sections = normalized_payload.get("sections")
            if not isinstance(sections, list):
                return
            section_bodies = [
                str(section.get("body") or "").strip()
                for section in sections
                if isinstance(section, dict) and str(section.get("body") or "").strip()
            ]
            if not section_bodies:
                return
            source_text = "\n\n".join(section_bodies)

        auto_promote = policy_mode == _MODE_AUDIT_REPAIR_PROMOTE and source_transcript_ref is not None
        run_id = f"tx_post_t0_{int(time.time())}_{hashlib.sha256((dossier_id + str(transcription_id or '')).encode('utf-8')).hexdigest()[:8]}"
        self.transcription_edit_run_registry.create_run(
            run_id=run_id,
            request={
                "dossier_id": dossier_id,
                "transcription_id": transcription_id,
                "mode": policy_mode,
                "execution": execution_mode,
                "input_kind": input_kind,
                "best_result_index": best_result_index,
                "auto_promote": auto_promote,
                "trigger": "post_t0",
            },
        )
        logger.info(
            "transcript_edit_agent_post_t0_trigger %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "dossier_id": dossier_id,
                    "transcription_id": transcription_id,
                            "mode": policy_mode,
                            "execution": execution_mode,
                            "input_kind": input_kind,
                            "best_result_index": best_result_index,
                            "auto_promote": auto_promote,
                        },
                        ensure_ascii=False,
                    ),
        )

        def _run_once() -> None:
            try:
                session_manager = KernelSessionManager(
                    action_executor=ActionExecutor(
                        deps=ActionExecutorDeps(
                            transcript_auditor=TranscriptAuditTool(),
                            transcript_span_opener=TranscriptSpanOpenerTool(),
                            transcript_plan_applier=TranscriptEditPlanApplyTool(),
                            transcript_promoter=TranscriptMappingPromoterTool(),
                        )
                    ),
                    persistence_service=RunArtifactPersistenceService(),
                )
                result = run_transcript_edit_controller_loop(
                    session_manager=session_manager,
                    request=TranscriptEditAgentRunRequest(
                        dossier_id=dossier_id,
                        source_transcript_ref=source_transcript_ref,
                        source_text=source_text,
                        max_iterations=3,
                        mode=policy_mode,
                        auto_promote=auto_promote,
                    ),
                    request_id_prefix=f"tx-post-t0-{transcription_id or 'adhoc'}",
                )
                self.transcription_edit_run_registry.update_run(
                    run_id=run_id,
                    patch={
                        "status": result.status,
                        "snapshot": {
                            "status": result.status,
                            "reason_code": result.reason_code,
                            "iterations": result.iterations,
                            "session_id": result.session_id,
                            "run_artifact_ref": result.run_artifact_ref,
                            "latest_refs": result.latest_refs,
                            "review_required": result.review_required,
                        },
                    },
                )
                logger.info(
                    "transcript_edit_agent_post_t0_completed %s",
                    json.dumps(
                        {
                            "run_id": run_id,
                            "dossier_id": dossier_id,
                            "transcription_id": transcription_id,
                            "status": result.status,
                            "reason_code": result.reason_code,
                            "iterations": result.iterations,
                            "review_required": result.review_required,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                self.transcription_edit_run_registry.update_run(
                    run_id=run_id,
                    patch={"status": "failed", "error": str(exc)},
                )
                logger.warning("transcript_edit_agent_post_t0_failed: %s", str(exc))
        if execution_mode == "sync":
            _run_once()
            return
        threading.Thread(target=_run_once, daemon=True).start()

    def _resolve_post_t0_source_transcript_ref(
        self,
        *,
        dossier_id: str,
        transcription_id: str | None,
        best_result_index: int | None = None,
    ) -> str | None:
        if not transcription_id:
            return None
        raw_root = (
            dossiers_root()
            / "views"
            / "transcriptions"
            / str(dossier_id)
            / str(transcription_id)
            / "raw"
        )
        if isinstance(best_result_index, int) and best_result_index >= 0:
            draft_num = best_result_index + 1
            versioned = raw_root / f"{transcription_id}_v{draft_num}.json"
            if versioned.exists():
                return str(versioned)
        ref = (
            raw_root
            / f"{transcription_id}.json"
        )
        if ref.exists():
            return str(ref)
        return None

    def _post_t0_tx_agent_mode(self) -> str:
        raw = str(os.getenv("PLATTERA_POST_T0_TX_AGENT_MODE", "")).strip().lower()
        if raw in {_MODE_OFF, _MODE_AUDIT_ONLY, _MODE_AUDIT_REPAIR, _MODE_AUDIT_REPAIR_PROMOTE}:
            return raw
        return _MODE_AUDIT_REPAIR_PROMOTE

    def _post_t0_tx_agent_execution(self) -> str:
        raw = str(os.getenv("PLATTERA_POST_T0_TX_AGENT_EXECUTION", "")).strip().lower()
        if raw in {"background_thread", "sync"}:
            return raw
        return "background_thread"

    def _persist_json_extraction_metric(
        self,
        *,
        extraction_mode: str,
        model: str,
        validation_passed: bool,
        repair_invoked: bool,
        recovered: bool,
        repair_snapshot_ref: str | None,
        raw_output_ref: str | None,
        context: dict[str, Any],
    ) -> None:
        try:
            mode = self._json_mode_kind(extraction_mode)
            if mode not in {"relaxed", "strict"}:
                return
            dossier_id = str(context.get("dossier_id") or "adhoc")
            self.transcription_edit_persistence.save_json_extraction_metric(
                dossier_id=dossier_id,
                payload={
                    "artifact_type": "json_extraction_metric_v1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mode": mode,
                    "model": model,
                    "validation_passed": bool(validation_passed),
                    "repair_invoked": bool(repair_invoked),
                    "recovered": bool(recovered),
                    "repair_snapshot_ref": repair_snapshot_ref,
                    "raw_output_ref": raw_output_ref,
                    "context": context,
                },
            )
        except Exception:
            pass

    def _validate_legal_document_json_payload(self, payload_text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(payload_text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            validated = _LegalDocumentV0.model_validate(payload)
        except ValidationError:
            return None
        normalized_sections = [
            {"id": idx + 1, "body": str(section.body)}
            for idx, section in enumerate(validated.sections)
            if str(section.body).strip()
        ]
        if not normalized_sections:
            return None
        return {
            "documentId": str(validated.documentId),
            "sections": normalized_sections,
        }

    def _persist_relaxed_raw_output_for_postmortem(
        self,
        *,
        raw_output: str,
        model: str,
        context: dict[str, Any],
    ) -> str | None:
        try:
            dossier_id = str(context.get("dossier_id") or "adhoc")
            return self.transcription_edit_persistence.save_raw_model_output(
                dossier_id=dossier_id,
                payload={
                    "artifact_type": "relaxed_json_raw_output",
                    "model": model,
                    "context": context,
                    "raw_output": raw_output,
                },
            )
        except Exception:
            return None

    def _repair_relaxed_json_with_edit_loop(
        self,
        *,
        raw_output: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            dossier_id = context.get("dossier_id")
            request = TranscriptionEditRunRequestV0(
                start=EditLoopStartRequestV0(
                    dossier_id=str(dossier_id) if dossier_id else None,
                    source_text=raw_output,
                    mode="repair",
                ),
                plan=None,
                promote_for_mapping=False,
            )
            snapshot = self.transcription_edit_run_service.run(request)
            artifact_ref = snapshot.source_transcript_ref
            payload = json.loads(Path(artifact_ref).read_text(encoding="utf-8"))
            sections_raw = payload.get("sections", []) if isinstance(payload, dict) else []
            sections: list[dict[str, Any]] = []
            for idx, section in enumerate(sections_raw):
                if not isinstance(section, dict):
                    continue
                body = section.get("body")
                if not isinstance(body, str) or not body.strip():
                    continue
                sections.append({"id": idx + 1, "body": body})
            if not sections:
                return None, artifact_ref
            normalized = {"documentId": "repaired", "sections": sections}
            return normalized, artifact_ref
        except Exception:
            return None, None
    
    def _prepare_image(self, image_path: str, enhancement_settings: dict = None) -> Tuple[str, str]:
        """Enhanced with bulletproof error handling"""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                logger.error(f"Image path does not exist: {image_path}")
                return None, None
            
            # Validate enhancement settings
            if enhancement_settings:
                try:
                    contrast = float(enhancement_settings.get('contrast', 2.0))
                    sharpness = float(enhancement_settings.get('sharpness', 2.0))
                    brightness = float(enhancement_settings.get('brightness', 1.5))
                    color = max(0.0, min(3.0, float(enhancement_settings.get('color', 1.0))))
                    
                    logger.info(f"Using enhancement settings: C:{contrast}, S:{sharpness}, B:{brightness}, Col:{color}")
                    
                    enhanced_image_data, image_format = enhance_for_character_recognition(
                        str(image_path),
                        contrast=contrast,
                        sharpness=sharpness,
                        brightness=brightness,
                        color=color
                    )
                except Exception as e:
                    logger.warning(f"Enhancement settings parsing failed: {e}, using defaults")
                    enhanced_image_data, image_format = enhance_for_character_recognition(str(image_path))
            else:
                # Use default enhancement settings
                enhanced_image_data, image_format = enhance_for_character_recognition(str(image_path))
            
            # Validate results
            if not enhanced_image_data:
                logger.error("Image enhancement returned empty data")
                return None, None
            
            return enhanced_image_data, image_format
            
        except Exception as e:
            logger.error(f"Failed to prepare image: {str(e)}")
            return None, None
    
    def _standardize_response(self, result: dict, model: str, service) -> dict:
        """
        Standardize response format across different services
        
        🔴 CRITICAL RESPONSE FORMATTING - FRONTEND DEPENDS ON THIS 🔴
        
        CRITICAL FIELDS:
        - "extracted_text": The main text content (REQUIRED by frontend)
        - "success": Boolean status (REQUIRED)
        - "model_used": Model identifier (REQUIRED)
        - "service_type": Service type (REQUIRED)
        - "tokens_used": Token count (OPTIONAL but useful)
        """
        if not result.get("success", False):
            return result
            
        # CRITICAL: Add consistent metadata while preserving extracted_text
        # Frontend specifically looks for "extracted_text" field
        return {
            "success": True,
            "extracted_text": result.get("extracted_text", ""),  # CRITICAL: Frontend dependency
            "model_used": model,
            "service_type": "llm" if hasattr(service, 'process_image_with_text') else "ocr",
            "service_name": service.__class__.__name__.lower().replace('service', ''),
            "tokens_used": result.get("tokens_used"),
            "confidence_score": result.get("confidence_score"),
            "metadata": {
                "processing_time": result.get("processing_time"),
                "image_dimensions": result.get("image_dimensions"),
                "file_size": result.get("file_size"),
                **result.get("metadata", {})
            }
        }
    
    def get_available_models(self) -> dict:
        """Get models available for image-to-text processing"""
        all_models = self.registry.get_all_models()
        
        # Filter for models that can process images
        image_models = {}
        for model_id, model_info in all_models.items():
            if model_info.get("capabilities", {}).get("image_processing", False):
                image_models[model_id] = model_info
                
        return image_models
    
    def get_extraction_modes(self) -> dict:
        """Get available extraction modes - DEPRECATED, use prompts.image_to_text.get_available_extraction_modes() instead"""
        # Import here to avoid circular dependencies
        from prompts.image_to_text import get_available_extraction_modes
        return get_available_extraction_modes()
    
    def process_with_redundancy(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document_json_relaxed",
                               enhancement_settings: dict = None, redundancy_count: int = 3, consensus_strategy: str = "sequential",
                               dossier_id: str = None, transcription_id: str = None, run_context: str = "solo") -> dict:
        """
        Process with redundancy using the dedicated RedundancyProcessor

        This method orchestrates redundancy processing while maintaining the same interface.
        All redundancy logic has been moved to the RedundancyProcessor class for better separation of concerns.

        Args:
            image_path: Path to the image file
            model: Model identifier to use
            extraction_mode: Extraction mode (legal_document_json, etc.)
            enhancement_settings: Image enhancement settings
            redundancy_count: Number of parallel calls
            consensus_strategy: Consensus algorithm to use
            dossier_id: Optional dossier ID for progressive saving
            transcription_id: Optional transcription ID for progressive saving
        """
        try:
            extraction_mode = self._effective_extraction_mode(extraction_mode)
            # Handle single redundancy by falling back to original method
            if redundancy_count <= 1:
                return self.process(image_path, model, extraction_mode, enhancement_settings)

            # Get service and prepare image (same as original process)
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }

            # Use same image preparation as original process
            image_data, image_format = self._prepare_image(image_path, enhancement_settings)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }

            # Use same prompt as original process
            prompt = get_image_to_text_prompt(extraction_mode, model)
            # Append optional user instruction if present
            try:
                ui = (enhancement_settings or {}).get('user_instruction')
                if ui:
                    prompt = f"{prompt}\n\nUser instruction:\n{ui}\n"
                    logger.info(f"🧩 Appended user instruction ({len(ui)} chars)")
            except Exception:
                pass

            # Set up progressive save callback if dossier context provided
            progressive_save_callback = None
            if dossier_id and transcription_id:
                logger.info(f"💾 PROGRESSIVE SAVING ENABLED for dossier {dossier_id}, transcription {transcription_id}")
                progressive_save_callback = self._create_progressive_save_callback(
                    dossier_id,
                    transcription_id,
                    extraction_mode=extraction_mode,
                    model=model,
                )
                logger.info("✅ Progressive save callback created and assigned")
            else:
                logger.info(f"⚠️ PROGRESSIVE SAVING DISABLED: dossier_id={dossier_id}, transcription_id={transcription_id}")

            # Delegate to redundancy processor
            json_mode = self._json_mode_kind(extraction_mode)
            result = self.redundancy_processor.process(
                service=service,
                image_data=image_data,
                image_format=image_format,
                prompt=prompt,
                model=model,
                redundancy_count=redundancy_count,
                json_mode=json_mode,
                progressive_save_callback=progressive_save_callback,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                run_context=run_context
            )
            return self._postprocess_legal_json_result(
                result=result,
                extraction_mode=extraction_mode,
                model=model,
                context={
                    "pipeline_method": "process_with_redundancy",
                    "run_context": run_context,
                    "dossier_id": dossier_id,
                    "transcription_id": transcription_id,
                },
            )

        except Exception as e:
            logger.error(f"Redundancy processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Redundancy processing failed: {str(e)}"
            }

    def _create_progressive_save_callback(
        self,
        dossier_id: str,
        transcription_id: str,
        *,
        extraction_mode: str,
        model: str,
    ):
        """
        Create a callback function for progressive draft saving.

        Args:
            dossier_id: The dossier identifier
            transcription_id: The transcription identifier

        Returns:
            Callback function that saves individual drafts
        """
        def progressive_save_callback(draft_index: int, result: dict):
            """Callback to save individual draft results progressively"""
            try:
                # Import here to avoid circular dependencies
                from services.dossier.progressive_draft_saver import ProgressiveDraftSaver

                saver = ProgressiveDraftSaver()
                success = saver.save_draft_result(
                    dossier_id,
                    transcription_id,
                    draft_index,
                    result,
                    extraction_mode_used=extraction_mode,
                    model_used=model,
                )

                if success:
                    logger.info(f"✅ Progressive save successful for draft v{draft_index + 1}")
                else:
                    logger.warning(f"⚠️ Progressive save failed for draft v{draft_index + 1}")

            except Exception as e:
                logger.error(f"❌ Progressive save callback failed for draft v{draft_index + 1}: {e}")

        return progressive_save_callback

    async def select_final_draft(
        self,
        redundancy_analysis: Dict[str, Any],
        alignment_result: Optional[Dict[str, Any]] = None,
        selected_draft: Union[int, str] = 'consensus',
        edited_draft_content: Optional[str] = None,
        edited_from_draft: Optional[Union[int, str]] = None
    ) -> Dict[str, Any]:
        """
        Select the final draft output from the image-to-text pipeline.
        
        Args:
            redundancy_analysis: Results from redundancy analysis
            alignment_result: Optional alignment results (for consensus)
            selected_draft: Which draft to select ('consensus', 'best', or draft index)
            edited_draft_content: Optional edited content
            edited_from_draft: Which draft was edited (if applicable)
            
        Returns:
            Final draft selection result
        """
        logger.info(f" FINAL DRAFT SELECTION REQUEST ► Draft: {selected_draft}")
        
        from .final_draft_selector import FinalDraftSelector
        selector = FinalDraftSelector()
        
        final_result = selector.select_final_draft(
            redundancy_analysis=redundancy_analysis,
            alignment_result=alignment_result,
            selected_draft=selected_draft,
            edited_draft_content=edited_draft_content,
            edited_from_draft=edited_from_draft
        )
        
        logger.info(f"✅ FINAL DRAFT SELECTION COMPLETE ► Method: {final_result['selection_method']}")
        return final_result

 
