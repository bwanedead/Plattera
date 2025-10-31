"""
Config Endpoints
================

Secure management for provider API keys via OS credential store.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import keyring
import os


router = APIRouter(prefix="/config", tags=["config"])

_SERVICE = "plattera"
_KEY_NAME = "openai_api_key"


class ApiKeyPayload(BaseModel):
    apiKey: str


@router.get("/key-status")
async def key_status():
    try:
        has_keyring = keyring.get_password(_SERVICE, _KEY_NAME) is not None
        has_env = bool(os.getenv("OPENAI_API_KEY"))
        return {"hasKey": bool(has_keyring or has_env)}
    except Exception as e:
        # If keyring backend is unavailable, still fall back to env var
        has_env = bool(os.getenv("OPENAI_API_KEY"))
        return {"hasKey": bool(has_env), "warning": f"keyring unavailable: {e}"}


@router.post("/key")
async def set_key(payload: ApiKeyPayload):
    try:
        if not payload.apiKey or not isinstance(payload.apiKey, str):
            raise HTTPException(status_code=400, detail="apiKey is required")
        keyring.set_password(_SERVICE, _KEY_NAME, payload.apiKey)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store key: {e}")


