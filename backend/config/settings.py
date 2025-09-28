"""
Central configuration for backend settings.
"""
import os


# Image-to-Text queue batch cap (easy to change/remove later)
IMAGE_TO_TEXT_BATCH_MAX: int = int(os.getenv("IMAGE_TO_TEXT_BATCH_MAX", "20"))



