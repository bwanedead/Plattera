"""
Image Storage Service
====================

Handles storage and retrieval of original and processed images
associated with transcriptions and dossiers.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import uuid
from config.paths import dossiers_original_images_root, dossiers_processed_images_root

logger = logging.getLogger(__name__)


class ImageStorageService:
    """
    Service for managing image storage related to transcriptions and dossiers.

    Handles:
    - Original source images
    - Processed/enhanced images
    - Image retrieval and metadata
    - Storage cleanup
    """

    def __init__(self):
        self.original_images_dir = dossiers_original_images_root()
        self.processed_images_dir = dossiers_processed_images_root()

        # Create directories if they don't exist
        self.original_images_dir.mkdir(parents=True, exist_ok=True)
        self.processed_images_dir.mkdir(parents=True, exist_ok=True)

        logger.info("🖼️ Image Storage Service initialized")

    def save_original_image(self, image_path: str, transcription_id: str = None) -> Optional[str]:
        """
        Save a copy of the original image for future reference.

        Args:
            image_path: Path to the original image file
            transcription_id: Associated transcription ID (optional)

        Returns:
            str: Path to saved image or None if failed
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"❌ Original image not found: {image_path}")
                return None

            # Generate unique filename
            image_id = transcription_id or str(uuid.uuid4())
            file_extension = Path(image_path).suffix.lower()
            saved_filename = f"{image_id}_original{file_extension}"
            saved_path = self.original_images_dir / saved_filename

            # Copy the image
            shutil.copy2(image_path, saved_path)

            logger.info(f"💾 Saved original image: {saved_path}")
            return str(saved_path)

        except Exception as e:
            logger.error(f"❌ Failed to save original image: {e}")
            return None

    def save_processed_image(self, processed_image_data: bytes,
                           original_image_path: str, transcription_id: str = None,
                           format: str = "jpeg") -> Optional[str]:
        """
        Save processed/enhanced image data.

        Args:
            processed_image_data: Bytes of processed image
            original_image_path: Path to original image for reference
            transcription_id: Associated transcription ID (optional)
            format: Image format (jpeg, png, etc.)

        Returns:
            str: Path to saved processed image or None if failed
        """
        try:
            # Generate unique filename
            image_id = transcription_id or str(uuid.uuid4())
            saved_filename = f"{image_id}_processed.{format}"
            saved_path = self.processed_images_dir / saved_filename

            # Write the processed image data
            with open(saved_path, 'wb') as f:
                f.write(processed_image_data)

            logger.info(f"💾 Saved processed image: {saved_path}")
            return str(saved_path)

        except Exception as e:
            logger.error(f"❌ Failed to save processed image: {e}")
            return None

    def get_original_image_path(self, transcription_id: str) -> Optional[str]:
        """
        Get the path to the original image for a transcription.

        Args:
            transcription_id: The transcription ID

        Returns:
            str: Path to original image or None if not found
        """
        try:
            # Look for original image with this transcription ID
            pattern = f"{transcription_id}_original.*"
            for file_path in self.original_images_dir.glob(pattern):
                return str(file_path)

            logger.warning(f"⚠️ Original image not found for transcription: {transcription_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error finding original image: {e}")
            return None

    def get_processed_image_path(self, transcription_id: str) -> Optional[str]:
        """
        Get the path to the processed image for a transcription.

        Args:
            transcription_id: The transcription ID

        Returns:
            str: Path to processed image or None if not found
        """
        try:
            # Look for processed image with this transcription ID
            pattern = f"{transcription_id}_processed.*"
            for file_path in self.processed_images_dir.glob(pattern):
                return str(file_path)

            logger.warning(f"⚠️ Processed image not found for transcription: {transcription_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error finding processed image: {e}")
            return None

    def get_image_info(self, transcription_id: str) -> Dict[str, Any]:
        """
        Get information about images associated with a transcription.

        Args:
            transcription_id: The transcription ID

        Returns:
            dict: Image information including paths and metadata
        """
        original_path = self.get_original_image_path(transcription_id)
        processed_path = self.get_processed_image_path(transcription_id)

        info = {
            "transcription_id": transcription_id,
            "has_original": original_path is not None,
            "has_processed": processed_path is not None,
            "original_path": original_path,
            "processed_path": processed_path
        }

        # Add file size information if files exist
        if original_path and os.path.exists(original_path):
            info["original_size_bytes"] = os.path.getsize(original_path)

        if processed_path and os.path.exists(processed_path):
            info["processed_size_bytes"] = os.path.getsize(processed_path)

        return info

    def delete_images(self, transcription_id: str) -> bool:
        """
        Delete all images associated with a transcription.

        Args:
            transcription_id: The transcription ID

        Returns:
            bool: Success status
        """
        try:
            deleted_count = 0

            # Delete original images
            original_pattern = f"{transcription_id}_original.*"
            for file_path in self.original_images_dir.glob(original_pattern):
                file_path.unlink()
                deleted_count += 1
                logger.info(f"🗑️ Deleted original image: {file_path}")

            # Delete processed images
            processed_pattern = f"{transcription_id}_processed.*"
            for file_path in self.processed_images_dir.glob(processed_pattern):
                file_path.unlink()
                deleted_count += 1
                logger.info(f"🗑️ Deleted processed image: {file_path}")

            logger.info(f"✅ Deleted {deleted_count} images for transcription: {transcription_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete images for transcription {transcription_id}: {e}")
            return False

    def cleanup_orphaned_images(self, active_transcription_ids: list) -> int:
        """
        Clean up images that are no longer associated with any transcription.

        Args:
            active_transcription_ids: List of transcription IDs that should be kept

        Returns:
            int: Number of orphaned images deleted
        """
        try:
            deleted_count = 0
            active_set = set(active_transcription_ids)

            # Check original images
            for file_path in self.original_images_dir.glob("*_original.*"):
                transcription_id = file_path.stem.split('_')[0]
                if transcription_id not in active_set:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted orphaned original image: {file_path}")

            # Check processed images
            for file_path in self.processed_images_dir.glob("*_processed.*"):
                transcription_id = file_path.stem.split('_')[0]
                if transcription_id not in active_set:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted orphaned processed image: {file_path}")

            logger.info(f"🧹 Cleaned up {deleted_count} orphaned images")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup orphaned images: {e}")
            return 0

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics for images.

        Returns:
            dict: Storage statistics
        """
        try:
            original_count = len(list(self.original_images_dir.glob("*_original.*")))
            processed_count = len(list(self.processed_images_dir.glob("*_processed.*")))

            original_size = 0
            for file_path in self.original_images_dir.glob("*_original.*"):
                original_size += file_path.stat().st_size

            processed_size = 0
            for file_path in self.processed_images_dir.glob("*_processed.*"):
                processed_size += file_path.stat().st_size

            return {
                "original_images_count": original_count,
                "processed_images_count": processed_count,
                "total_images_count": original_count + processed_count,
                "original_images_size_mb": round(original_size / (1024 * 1024), 2),
                "processed_images_size_mb": round(processed_size / (1024 * 1024), 2),
                "total_size_mb": round((original_size + processed_size) / (1024 * 1024), 2)
            }

        except Exception as e:
            logger.error(f"❌ Failed to get storage stats: {e}")
            return {
                "error": str(e),
                "original_images_count": 0,
                "processed_images_count": 0,
                "total_images_count": 0,
                "original_images_size_mb": 0,
                "processed_images_size_mb": 0,
                "total_size_mb": 0
            }
