"""
Redundancy Processing Module
===========================

Handles parallel API execution, result analysis, and redundancy response formatting.
"""

import logging
import time
import random
import concurrent.futures
from typing import List, Dict, Any, Optional
from services.registry import get_registry
from prompts.redundancy_consensus import build_consensus_prompt

from utils.text_utils import filter_valid_extractions

logger = logging.getLogger(__name__)


class RedundancyProcessor:
    """Handles complete redundancy workflow for image-to-text processing"""
    def __init__(self):
        # Optional LLM consensus configuration (set by pipeline/controller)
        self.auto_llm_consensus: bool = False
        self.llm_consensus_model: str = "gpt-5-consensus"  # default alias
    
    def process(self, service, image_data: str, image_format: str, prompt: str, model: str,
               redundancy_count: int, json_mode: bool = False,
               progressive_save_callback: callable = None,
               dossier_id: Optional[str] = None,
               transcription_id: Optional[str] = None,
               run_context: str = "solo",
               lane_progress_callback: callable = None) -> dict:
        """
        Complete redundancy processing workflow with optional progressive saving

        Args:
            service: The service to use for processing
            image_data: Base64 encoded image data
            image_format: Image format string
            prompt: Processing prompt
            model: Model identifier
            redundancy_count: Number of parallel calls to make
            json_mode: Whether to enable JSON mode
            progressive_save_callback: Optional callback for saving drafts progressively
                Signature: callback(draft_index: int, result: dict) -> None

        Returns:
            dict: Fully formatted redundancy response
        """
        ctx_parts = [f"run={run_context}"]
        if dossier_id:
            ctx_parts.append(f"dossier={dossier_id}")
        if transcription_id:
            ctx_parts.append(f"transcription={transcription_id}")
        ctx = " ".join(ctx_parts)
        logger.info(f"🧭 RUN CONTEXT ► {ctx}")
        logger.info(f"🚀 REDUNDANCY PROCESSING ► Starting {redundancy_count} parallel calls")
        if progressive_save_callback:
            logger.debug("💾 PROGRESSIVE SAVING ENABLED ► Drafts will be saved as they complete")

        # Execute parallel API calls with optional progressive saving
        parallel_results = self._execute_parallel_calls(
            service, image_data, image_format, prompt, model, redundancy_count, json_mode,
            progressive_save_callback, dossier_id, transcription_id, run_context, lane_progress_callback
        )

        # Analyze results and format response
        logger.info("🧠 CONSENSUS ANALYSIS ► Starting redundancy analysis...")
        final_result = self._analyze_results(
            parallel_results,
            model,
            run_context=run_context,
            dossier_id=dossier_id,
            transcription_id=transcription_id
        )
        logger.info("✅ CONSENSUS COMPLETE ► Analysis finished successfully")

        return final_result
    
    def _execute_parallel_calls(self, service, image_data: str, image_format: str, prompt: str,
                               model: str, count: int, json_mode: bool = False,
                               progressive_save_callback: callable = None,
                               dossier_id: Optional[str] = None,
                               transcription_id: Optional[str] = None,
                               run_context: str = "solo",
                               lane_progress_callback: callable = None) -> List[dict]:
        """Execute multiple API calls with improved staggering and jitter to reduce empty responses"""
        results = []
        started_mono = time.perf_counter()

        logger.info(f"🚀 API EXECUTION ► Starting {count} parallel calls with staggered timing (run={run_context})")
        if progressive_save_callback:
            logger.debug("💾 PROGRESSIVE CALLBACK ACTIVE ► Will save drafts as they complete")

        # Increased base delay + added jitter for o4-mini reliability
        base_stagger_delay = 1.5  # Increased from 700ms to 1500ms for o4-mini

        # Use ThreadPoolExecutor for parallel API calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            # Submit calls with staggered timing + jitter
            futures = []
            for i in range(count):
                if i > 0:  # Add delay before subsequent calls
                    # Add random jitter (200-800ms) to prevent exact timing collisions
                    jitter = random.uniform(0.2, 0.8)
                    total_delay = base_stagger_delay + jitter
                    time.sleep(total_delay)
                    logger.debug(f"⏱️  API CALL {i+1} ► Submitted after {total_delay:.2f}s delay (base {base_stagger_delay}s + jitter {jitter:.2f}s)")

                # Pass explicit max_tokens to reduce cutoffs
                future = executor.submit(
                    service.process_image_with_text,
                    image_data=image_data,
                    prompt=prompt,
                    model=model,
                    image_format=image_format,
                    json_mode=json_mode,
                    run_context=run_context,
                    draft_index=i,
                    draft_count=count,
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                    # Do NOT override max tokens here; let the service profile decide.
                )
                futures.append((i, future))  # Store index with future

                if i == 0:
                    logger.debug(f"⚡ API CALL {i+1} ► Submitted immediately")

            # Collect results as they complete (not necessarily in order)
            for draft_index, future in futures:
                try:
                    # Increased timeout for o4-mini (2 min -> 4 min)
                    result = future.result(timeout=240)  # 4 minute timeout for long reasoning tasks
                    logger.info(f"✅ API CALL {draft_index+1} ► Completed successfully")

                    # Save result immediately if callback provided
                    if progressive_save_callback:
                        try:
                            progressive_save_callback(draft_index, result)
                            logger.debug(f"💾 PROGRESSIVE SAVE TRIGGERED ► Draft v{draft_index+1} saved")
                        except Exception as save_error:
                            logger.warning(f"⚠️ Progressive save failed for draft v{draft_index+1}: {save_error}")

                    results.append(result)
                    logger.info(
                        "AGENT_VIEWER_TIMING ► t0_draft_returned draft=%s/%s success=%s elapsed_ms=%s run=%s dossier=%s transcription=%s",
                        draft_index + 1,
                        count,
                        bool(result.get("success", False)),
                        int((time.perf_counter() - started_mono) * 1000),
                        run_context,
                        dossier_id or "n/a",
                        transcription_id or "n/a",
                    )
                    if lane_progress_callback:
                        try:
                            lane_progress_callback(
                                {
                                    "phase": "t0_draft_result",
                                    "draft_index": draft_index + 1,
                                    "draft_total": count,
                                    "status": "completed" if bool(result.get("success", False)) else "failed",
                                    "elapsed_ms": int((time.perf_counter() - started_mono) * 1000),
                                }
                            )
                        except Exception:
                            pass
                except concurrent.futures.TimeoutError as e:
                    logger.error(f"⏳ API CALL {draft_index+1} ► Timed out after 240s")
                    failed_result = {
                        "success": False,
                        "error": "API call failed: timeout",
                        "extracted_text": "",
                        "metadata": {
                            "run_context": run_context,
                            "draft_index": draft_index,
                            "draft_count": count,
                            "dossier_id": dossier_id,
                            "transcription_id": transcription_id
                        }
                    }
                    if progressive_save_callback:
                        try:
                            progressive_save_callback(draft_index, failed_result)
                            logger.debug(f"💾 PROGRESSIVE SAVE TRIGGERED ► Draft v{draft_index+1} timed out, saved error state")
                        except Exception as save_error:
                            logger.warning(f"⚠️ Progressive save failed for timed-out draft v{draft_index+1}: {save_error}")
                    results.append(failed_result)
                    if lane_progress_callback:
                        try:
                            lane_progress_callback(
                                {
                                    "phase": "t0_draft_result",
                                    "draft_index": draft_index + 1,
                                    "draft_total": count,
                                    "status": "failed",
                                    "elapsed_ms": int((time.perf_counter() - started_mono) * 1000),
                                }
                            )
                        except Exception:
                            pass
                except Exception as e:
                    err_type = type(e).__name__
                    err_msg = str(e) or repr(e)
                    logger.error(f"❌ API CALL {draft_index+1} ► Failed: {err_type}: {err_msg}")
                    failed_result = {
                        "success": False,
                        "error": f"API call failed: {err_type}: {err_msg}",
                        "extracted_text": "",
                        "metadata": {
                            "run_context": run_context,
                            "draft_index": draft_index,
                            "draft_count": count,
                            "dossier_id": dossier_id,
                            "transcription_id": transcription_id
                        }
                    }

                    # Save failed result immediately if callback provided
                    if progressive_save_callback:
                        try:
                            progressive_save_callback(draft_index, failed_result)
                            logger.debug(f"💾 PROGRESSIVE SAVE TRIGGERED ► Draft v{draft_index+1} failed, saved error state")
                        except Exception as save_error:
                            logger.warning(f"⚠️ Progressive save failed for failed draft v{draft_index+1}: {save_error}")

                    results.append(failed_result)
                    if lane_progress_callback:
                        try:
                            lane_progress_callback(
                                {
                                    "phase": "t0_draft_result",
                                    "draft_index": draft_index + 1,
                                    "draft_total": count,
                                    "status": "failed",
                                    "elapsed_ms": int((time.perf_counter() - started_mono) * 1000),
                                }
                            )
                        except Exception:
                            pass

        successful_count = sum(1 for r in results if r.get("success", False))
        logger.info(f"📊 API EXECUTION COMPLETE ► {successful_count}/{count} calls successful")

        return results
    
    def _analyze_results(self, results: List[dict], model: str,
                        run_context: Optional[str] = None,
                        dossier_id: Optional[str] = None,
                        transcription_id: Optional[str] = None) -> dict:
        """Analyze multiple results to find consensus - simplified without alignment"""
        
        logger.debug(f"🔍 CONSENSUS ANALYSIS ► Starting redundancy analysis on {len(results)} API calls")
        
        # Continue with consensus analysis...
        logger.debug("🔍 CONSENSUS INPUT ► Filtering successful results...")
        successful_results = [r for r in results if r.get("success", False)]
        logger.debug(f"   ✅ Found {len(successful_results)}/{len(results)} successful API calls")
        
        if not successful_results:
            logger.info("❌ CONSENSUS FAILED ► No successful results to analyze")
            return self._format_error_response(
                "All processing attempts failed",
                "No successful results", 
                model,
                len(results)
            )
        
        # Filter out LLM refusals and failed extractions
        logger.debug("🔧 CONSENSUS FILTERING ► Removing failed extractions...")
        filtered_texts = filter_valid_extractions([r.get("extracted_text", "") for r in successful_results])
        logger.debug(f"   📊 Using {len(filtered_texts)} high-quality extractions")
        
        if not filtered_texts:
            logger.info("❌ CONSENSUS FAILED ► No valid extractions after filtering")
            return self._format_error_response(
                "All extractions were invalid or refused",
                "No valid extractions after filtering",
                model,
                len(results),
                successful_calls=len(successful_results)
            )
        
        # Simple draft selection - pick the longest/best result without complex alignment
        logger.info(f"📋 DRAFT SELECTION ► Selecting best from {len(filtered_texts)} valid extractions")
        
        # Find the longest text as the "best" result
        best_text = max(filtered_texts, key=len)
        best_result_index = 0
        
        # Find which original result corresponds to our best text
        filtered_results = []
        for result in successful_results:
            result_text = result.get("extracted_text", "")
            if result_text in filtered_texts:
                filtered_results.append(result)
                if result_text == best_text:
                    best_result_index = len(filtered_results) - 1
        
        # Aggregate token usage
        total_tokens = sum(r.get("tokens_used", 0) for r in successful_results)
        
        logger.info(f"✅ DRAFT SELECTED ► Using result {best_result_index + 1}/{len(filtered_results)} (length: {len(best_text)} chars)")
        
        # Optional: generate LLM consensus when enabled
        consensus_payload: Dict[str, Any] = {}
        if self.auto_llm_consensus:
            try:
                if len(filtered_texts) > 1:
                    logger.info(f"🤝 LLM CONSENSUS ► Generating using model: {self.llm_consensus_model}")
                    consensus_payload = self._generate_llm_consensus(
                        filtered_texts,
                        run_context=run_context,
                        dossier_id=dossier_id,
                        transcription_id=transcription_id
                    )
                else:
                    logger.info("🤝 LLM CONSENSUS ► Only 1 valid draft; running title/cleanup pass")
                    consensus_payload = self._generate_llm_consensus(
                        filtered_texts,
                        run_context=run_context,
                        dossier_id=dossier_id,
                        transcription_id=transcription_id
                    )
                if consensus_payload.get("text"):
                    logger.info(f"✅ LLM CONSENSUS ► Received consensus text ({len(consensus_payload['text'])} chars)")
                if consensus_payload.get("title"):
                    logger.info(f"🏷️ LLM CONSENSUS ► Extracted title: {consensus_payload['title']}")
            except Exception as e:
                logger.warning(f"⚠️ LLM consensus generation failed (non-critical): {e}")

        return self._format_success_response(
            best_text, model, total_tokens, results, successful_results,
            filtered_texts, best_result_index, consensus=consensus_payload
        )
    
    def _format_success_response(self, best_text: str, model: str, total_tokens: int,
                               all_results: List[dict], successful_results: List[dict],
                               filtered_texts: List[str], best_result_index: int,
                               consensus: Dict[str, Any] | None = None) -> dict:
        """Format successful redundancy response with complete metadata"""
        resp = {
            "success": True,
            "extracted_text": best_text,
            "model_used": model,
            "service_type": "llm",
            "tokens_used": total_tokens,
            "confidence_score": 1.0,  # Single draft = full confidence
            "metadata": {
                "redundancy_enabled": True,
                "redundancy_count": len(all_results),
                "processing_mode": "draft_selection",
                "best_result_used": best_result_index + 1,
                "redundancy_analysis": {
                    "total_calls": len(all_results),
                    "successful_calls": len(successful_results),
                    "valid_extractions": len(filtered_texts),
                    "filtered_out": len(successful_results) - len(filtered_texts),
                    "failed_calls": len(all_results) - len(successful_results),
                    "best_result_index": best_result_index,
                    "individual_results": [
                        {
                            "success": r.get("success", False),
                            "text": r.get("extracted_text", ""),
                            "tokens": r.get("tokens_used", 0),
                            "error": r.get("error")
                        }
                        for r in all_results
                    ]
                }
            }
        }

        # Attach LLM consensus data if available
        try:
            if consensus and isinstance(consensus, dict) and consensus.get("text"):
                ra = resp["metadata"].get("redundancy_analysis", {})
                ra["consensus_text"] = consensus.get("text", "")
                if consensus.get("title"):
                    ra["consensus_title"] = consensus.get("title")
                ra["consensus_model"] = consensus.get("model") or self.llm_consensus_model
                if consensus.get("tokens") is not None:
                    ra["consensus_tokens_used"] = consensus.get("tokens")
                ra["consensus_source"] = "llm"
                resp["metadata"]["redundancy_analysis"] = ra
        except Exception as e:
            logger.warning(f"⚠️ Failed to attach LLM consensus (non-critical): {e}")

        return resp
    
    def _format_error_response(self, error_text: str, error_reason: str, model: str, 
                             total_calls: int, successful_calls: int = 0) -> dict:
        """Format error response for failed redundancy processing"""
        return {
            "success": False,
            "extracted_text": error_text,
            "error": error_reason, 
            "model_used": model,
            "service_type": "llm",
            "tokens_used": 0,
            "confidence_score": 0.0,
            "metadata": {
                "redundancy_enabled": True,
                "redundancy_count": total_calls,
                "processing_mode": "failed" if successful_calls == 0 else "filtered_out",
                "successful_calls": successful_calls,
                "failed_calls": total_calls - successful_calls
            }
        } 

    def _generate_llm_consensus(self, drafts: List[str],
                                run_context: Optional[str] = None,
                                dossier_id: Optional[str] = None,
                                transcription_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate LLM-based consensus with retry and higher token cap."""
        registry = get_registry()
        prompt = build_consensus_prompt(drafts)
        model = self.llm_consensus_model or "gpt-5-consensus"

        attempts = 3
        last_error = None
        for i in range(attempts):
            try:
                # Delegate token limits to service profile; only vary temperature slightly across attempts
                temp = 0.2 if i < 2 else 0.1
                res = registry.process_text(
                    prompt=prompt,
                    model=model,
                    temperature=temp,
                    run_context=run_context or "solo",
                    phase="consensus",
                    dossier_id=dossier_id,
                    transcription_id=transcription_id
                )
                if res and res.get("success") and res.get("text"):
                    raw = res.get("text") or ""
                    tokens = res.get("tokens_used")

                    # Parse optional title
                    title = None
                    text_out = raw.strip()
                    lines = text_out.splitlines()
                    if lines:
                        first = lines[0].strip()
                        if first.lower().startswith("title:"):
                            title = first.split(":", 1)[1].strip()
                            body = lines[1:]
                            if body and body[0].strip() == "":
                                body = body[1:]
                            text_out = "\n".join(body).strip()

                    # Fallback: if no body after parsing and drafts exist, use the longest draft as body
                    if not text_out.strip() and drafts:
                        text_out = max(drafts, key=len)

                    return {
                        "text": text_out,
                        "title": title,
                        "model": model,
                        "tokens": tokens,
                    }
                last_error = res.get("error") if res else "Unknown error"
            except Exception as e:
                last_error = str(e)

        logger.warning(f"⚠️ LLM consensus failed after {attempts} attempts: {last_error}")
        return {}
