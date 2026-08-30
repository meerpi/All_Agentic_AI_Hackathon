"""
Token / Cost Tracking Module.

Wraps every LLM call to capture prompt_tokens, completion_tokens,
total_tokens, model used, and estimated cost in USD.
"""

import logging
from typing import Any, Dict, Optional

from agent.models import TokenUsage

logger = logging.getLogger("taskmaster.telemetry")

# Cost per 1M tokens (2026 pricing approximations)
MODEL_PRICING = {
    # Gemini models
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-3.1-flash-lite-preview": {"input": 0.075, "output": 0.30},
    "gemini-3.6-flash": {"input": 0.15, "output": 0.60},
    "gemini-3.7-flash": {"input": 0.20, "output": 0.80},
    # Default fallback
    "default": {"input": 0.15, "output": 0.60},
}


def extract_token_usage(response: Any, model_name: str = "") -> TokenUsage:
    """
    Extract token usage from a Gemini API response object.
    Handles various response formats gracefully.
    """
    prompt_tokens = 0
    completion_tokens = 0

    try:
        # Gemini SDK response format
        if hasattr(response, "usage_metadata"):
            meta = response.usage_metadata
            prompt_tokens = getattr(meta, "prompt_token_count", 0) or 0
            completion_tokens = getattr(meta, "candidates_token_count", 0) or 0
        elif isinstance(response, dict):
            meta = response.get("usageMetadata", {})
            prompt_tokens = meta.get("promptTokenCount", 0)
            completion_tokens = meta.get("candidatesTokenCount", 0)
    except Exception as e:
        logger.debug(f"Token extraction failed: {e}")

    total = prompt_tokens + completion_tokens
    cost = estimate_cost(prompt_tokens, completion_tokens, model_name)

    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total,
        model_used=model_name,
        estimated_cost_usd=cost,
    )


def estimate_cost(prompt_tokens: int, completion_tokens: int,
                  model_name: str = "") -> float:
    """Estimate USD cost based on token counts and model pricing."""
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["default"])
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)
