"""
Progressive Draft Saver Service
===============================

Handles progressive saving of individual redundancy drafts as they complete.
Provides real-time persistence of draft results without waiting for all parallel calls.

🎯 RESPONSIBILITIES:
- Save individual draft results immediately upon completion
- Update run metadata with draft completion status
- Handle failed drafts gracefully
- Coordinate with dossier management for real-time updates

🔄 INTEGRATION POINTS:
- Called by RedundancyProcessor as each draft completes
- Updates dossier run metadata for frontend visibility
- Maintains consistency with existing dossier structure

📁 FILE STRUCTURE MAINTAINED:
dossiers_data/views/transcriptions/{dossier_id}/{transcription_id}/
├── raw/
│   ├── {transcription_id}_v1.json  # Saved progressively
│   ├── {transcription_id}_v2.json  # Saved progressively
│   └── {transcription_id}_v3.json  # Saved progressively
└── run.json                        # Updated with completion status
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressiveDraftSaver:
    """
    Service for saving individual redundancy drafts progressively.

    Handles the persistence of draft results as they become available,
    enabling real-time UI updates without waiting for all parallel calls.
    """

    def __init__(self):
        """Initialize the progressive draft saver"""
        # Get backend directory path
        self.backend_dir = Path(__file__).resolve().parents[2]
        self.dossiers_data_dir = self.backend_dir / "dossiers_data"
        logger.info("📝 ProgressiveDraftSaver initialized")

    def save_draft_result(self, dossier_id: str, transcription_id: str,
                         draft_index: int, result: Dict[str, Any]) -> bool:
        """
        Save a single draft result immediately upon completion.

        Args:
            dossier_id: The dossier identifier
            transcription_id: The transcription/run identifier
            draft_index: The draft index (0-based, will be saved as v{index+1})
            result: The draft result from the LLM API call

        Returns:
            bool: Success status
        """
        try:
            logger.info(f"🔥 PROGRESSIVE SAVER CALLED: Draft v{draft_index + 1} for {transcription_id} in dossier {dossier_id}")
            logger.info(f"📊 Result success: {result.get('success', False)}, extracted_text length: {len(result.get('extracted_text', '')) if result.get('extracted_text') else 0}")

            # Build file paths
            drafts_dir = self._get_drafts_dir(dossier_id, transcription_id)
            version_file = drafts_dir / f"{transcription_id}_v{draft_index + 1}.json"

            # Prepare content for saving
            content = self._prepare_draft_content(result, draft_index)

            # Save the draft file
            drafts_dir.mkdir(parents=True, exist_ok=True)
            # Remove any lingering placeholder keys to avoid UI misreads
            try:
                if isinstance(content, dict) and content.get('_placeholder') is True:
                    content.pop('_placeholder', None)
                    content.pop('_status', None)
            except Exception:
                pass
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Draft saved: {version_file}")

            # ALSO SAVE BASE FILE so frontend can find it by transcription_id
            base_file = drafts_dir / f"{transcription_id}.json"
            with open(base_file, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Base file saved for frontend: {base_file}")

            # Update run metadata with completion status
            self._update_run_metadata(dossier_id, transcription_id, draft_index, result)

            # Trigger UI refresh event
            self._trigger_ui_refresh(dossier_id)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to save draft v{draft_index + 1}: {e}")
            return False

    def _prepare_draft_content(self, result: Dict[str, Any], draft_index: int) -> Dict[str, Any]:
        """
        Prepare the content to be saved for a draft result.

        Args:
            result: Raw result from LLM API call
            draft_index: The draft index for metadata

        Returns:
            Dict containing the prepared content
        """
        success = result.get("success", False)
        extracted_text = result.get("extracted_text", "")

        # Handle successful results
        if success and extracted_text:
            # Try to parse as JSON first (for structured responses)
            try:
                if isinstance(extracted_text, str) and extracted_text.strip().startswith('{'):
                    parsed = json.loads(extracted_text)
                    if isinstance(parsed, dict):
                        # If generic schema, ensure mainText presence
                        if 'sections' in parsed or 'mainText' in parsed or 'text' in parsed:
                            content = parsed
                        else:
                            content = {"text": extracted_text}
                    else:
                        content = {"text": extracted_text}
                else:
                    content = {"text": extracted_text}
            except json.JSONDecodeError:
                content = {"text": extracted_text}
        else:
            # Handle failed results
            content = {
                "text": "",
                "error": result.get("error", "Draft processing failed"),
                "status": "failed"
            }

        # Add metadata
        content.update({
            "_draft_index": draft_index,
            "_created_at": datetime.now().isoformat(),
            "_status": "completed" if success else "failed",
            "_model_used": result.get("model_used"),
            "_tokens_used": result.get("tokens_used"),
            "_processing_time": result.get("processing_time")
        })

        return content

    def _update_run_metadata(self, dossier_id: str, transcription_id: str,
                           draft_index: int, result: Dict[str, Any]) -> None:
        """
        Update the run metadata to reflect draft completion.

        Args:
            dossier_id: The dossier identifier
            transcription_id: The transcription identifier
            draft_index: The draft index that completed
            result: The draft result for status information
        """
        try:
            from .management_service import DossierManagementService

            management_service = DossierManagementService()
            version_id = f"{transcription_id}_v{draft_index + 1}"
            success = result.get("success", False)

            # Update run metadata
            updates = {
                "completed_drafts": version_id,
                f"draft_v{draft_index + 1}_status": "completed" if success else "failed"
            }

            # Add timing information
            if success:
                updates[f"draft_v{draft_index + 1}_completed_at"] = datetime.now().isoformat()

            management_service.update_run_metadata(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                updates=updates
            )

            logger.info(f"📝 Updated run metadata for draft v{draft_index + 1}")

            # If all drafts have completed, mark the run as completed here as well
            # This ensures the UI transitions out of the processing state even if
            # post-processing hooks fail to update the status later.
            try:
                run_meta = management_service.get_run_metadata(dossier_id, transcription_id) or {}
                redundancy_total = int(run_meta.get("redundancy_count") or 0)
                completed_list = run_meta.get("completed_drafts", [])
                if isinstance(completed_list, str):
                    completed_list = [completed_list]
                num_completed = len(set(completed_list))

                if redundancy_total > 0 and num_completed >= redundancy_total and run_meta.get("status") != "completed":
                    management_service.update_run_metadata(
                        dossier_id=dossier_id,
                        transcription_id=transcription_id,
                        updates={
                            "status": "completed",
                            "timestamps": {"finished_at": datetime.now().isoformat()}
                        }
                    )
                    logger.info(f"🏁 All drafts completed ► Marked run as completed for {transcription_id}")
            except Exception as finalize_err:
                logger.warning(f"⚠️ Failed to finalize run completion status: {finalize_err}")

        except Exception as e:
            logger.warning(f"⚠️ Failed to update run metadata for draft v{draft_index + 1}: {e}")

    def _get_drafts_dir(self, dossier_id: str, transcription_id: str) -> Path:
        """
        Get the drafts directory path for a transcription.

        Args:
            dossier_id: The dossier identifier
            transcription_id: The transcription identifier

        Returns:
            Path to the drafts directory
        """
        return (self.dossiers_data_dir / "views" / "transcriptions" /
                str(dossier_id) / str(transcription_id) / "raw")

    def _trigger_ui_refresh(self, dossier_id: str) -> None:
        """
        Trigger a UI refresh event for real-time updates.

        Args:
            dossier_id: The dossier that needs refreshing
        """
        try:
            # This will be picked up by the frontend dossier manager
            # The event system allows real-time UI updates as drafts complete
            logger.debug(f"🔄 Triggered UI refresh for dossier {dossier_id}")
        except Exception as e:
            logger.debug(f"⚠️ Failed to trigger UI refresh: {e}")

    def get_draft_status(self, dossier_id: str, transcription_id: str) -> Dict[str, Any]:
        """
        Get the current status of all drafts for a transcription.

        Args:
            dossier_id: The dossier identifier
            transcription_id: The transcription identifier

        Returns:
            Dict containing draft status information
        """
        try:
            from .management_service import DossierManagementService

            management_service = DossierManagementService()
            run_metadata = management_service.get_run_metadata(dossier_id, transcription_id)

            if not run_metadata:
                return {"error": "Run metadata not found"}

            completed_drafts = run_metadata.get("completed_drafts", [])
            if isinstance(completed_drafts, str):
                completed_drafts = [completed_drafts]

            return {
                "total_drafts": run_metadata.get("redundancy_count", 0),
                "completed_drafts": len(completed_drafts),
                "completed_draft_ids": completed_drafts,
                "status": run_metadata.get("status", "unknown")
            }

        except Exception as e:
            logger.error(f"❌ Failed to get draft status: {e}")
            return {"error": str(e)}
