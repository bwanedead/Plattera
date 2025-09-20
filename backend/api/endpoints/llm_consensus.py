"""
LLM Consensus API Endpoints
===========================

Dedicated endpoints for generating LLM-based consensus drafts over multiple transcription texts.
This is distinct from the alignment-based consensus endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from services.registry import get_registry
from prompts.redundancy_consensus import build_consensus_prompt


logger = logging.getLogger(__name__)

router = APIRouter()


class LLMConsensusRequest(BaseModel):
    """Request for LLM-based consensus generation."""
    drafts: List[str] = Field(..., description="Transcription drafts to merge into a single consensus")
    model: str = Field(
        "gpt-5-consensus",
        description="Consensus model alias: gpt-5-consensus | gpt-5-mini-consensus | gpt-5-nano-consensus"
    )
    max_tokens: Optional[int] = Field(12000, description="Max output tokens for the consensus call")
    temperature: Optional[float] = Field(0.2, description="Sampling temperature")


class LLMConsensusResponse(BaseModel):
    success: bool
    consensus_text: Optional[str] = None
    consensus_title: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


@router.post("/generate", response_model=LLMConsensusResponse)
async def generate_llm_consensus(request: LLMConsensusRequest):
    """
    Produce a best-guess consensus transcription using an LLM over multiple drafts.
    This endpoint is independent from alignment-based consensus.
    """
    try:
        if not request.drafts or len([d for d in request.drafts if d and d.strip()]) < 2:
            raise HTTPException(status_code=400, detail="At least two non-empty drafts are required for LLM consensus")

        registry = get_registry()
        prompt = build_consensus_prompt(request.drafts)
        result = registry.process_text(
            prompt=prompt,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        if not result or not result.get("success"):
            return LLMConsensusResponse(
                success=False,
                error=result.get("error") if result else "Unknown error",
                metadata={"source": "llm", "consensus": True}
            )

        raw = result.get("text") or ""
        tokens = result.get("tokens_used")

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

        return LLMConsensusResponse(
            success=True,
            consensus_text=text_out,
            consensus_title=title,
            model_used=request.model,
            tokens_used=tokens,
            metadata={"source": "llm", "consensus": True}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM consensus generation failed: {e}")
        return LLMConsensusResponse(success=False, error=str(e), metadata={"source": "llm", "consensus": True})


