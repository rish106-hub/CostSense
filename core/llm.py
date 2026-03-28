"""
LangChain LLM client for Agent 4 (Root Cause Analysis).

Uses OpenRouter as the API gateway with three free-tier models in a fallback chain:
  Primary:    meta-llama/llama-3.1-8b-instruct:free
  Fallback 1: mistralai/mistral-7b-instruct:free
  Fallback 2: google/gemma-2-9b-it:free

The chain structure:
  ChatPromptTemplate → RunnableWithFallbacks (3 models) → PydanticOutputParser

On total failure, returns a safe default RootCauseResult so the pipeline continues.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class RootCauseResult(BaseModel):
    """Structured output from the LLM root cause chain."""

    explanation: str = Field(description="2-3 sentence root cause explanation")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    suggested_action: str = Field(description="Single actionable recommendation")
    model_used: str = Field(description="Model ID that produced this response")


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior financial analyst specializing in enterprise spend intelligence and procurement fraud detection. Your job is to analyze flagged financial transactions and identify root causes.

Rules:
- Be specific: name the vendor, amount, and most likely cause
- Be concise: explanation must be 2-3 sentences maximum
- Be actionable: suggested_action must be a single concrete step
- Confidence: 0.95+ for rule-based detections, 0.70-0.90 for ML detections

You MUST respond with ONLY valid JSON in this exact format — no markdown, no explanation:
{{"explanation": "...", "confidence": 0.85, "suggested_action": "...", "model_used": "{model_id}"}}"""

HUMAN_PROMPT = """ANOMALY ALERT
=============
Vendor:          {vendor}
Amount:          {currency} {amount:,.0f}
Category:        {category}
Department:      {department}
Date:            {transaction_date}
Invoice Number:  {invoice_number}

Detection Method: {anomaly_type}
Isolation Score:  {isolation_score}
Rule Flags:       {rule_flags}

Similar Past Anomalies:
{similar_anomalies}

Analyze this anomaly and respond with JSON only."""


# ---------------------------------------------------------------------------
# Chain builder
# ---------------------------------------------------------------------------


def _build_llm(model_id: str, api_key: str, base_url: str, timeout: int) -> ChatOpenAI:
    """Create a single ChatOpenAI instance pointing to OpenRouter."""
    return ChatOpenAI(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "256")),
        timeout=timeout,
        max_retries=0,  # Retries handled by tenacity at the agent level
    )


def build_root_cause_chain() -> RunnableSequence:
    """
    Build the full LangChain root cause analysis chain with model fallback.

    Returns a runnable that accepts a dict with anomaly context fields and
    produces a RootCauseResult.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "dummy-key")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    model_primary = os.getenv("LLM_MODEL_PRIMARY", "meta-llama/llama-3.1-8b-instruct:free")
    model_fallback_1 = os.getenv("LLM_MODEL_FALLBACK_1", "mistralai/mistral-7b-instruct:free")
    model_fallback_2 = os.getenv("LLM_MODEL_FALLBACK_2", "google/gemma-2-9b-it:free")

    primary = _build_llm(model_primary, api_key, base_url, timeout)
    fallback1 = _build_llm(model_fallback_1, api_key, base_url, timeout)
    fallback2 = _build_llm(model_fallback_2, api_key, base_url, timeout)

    # LangChain native fallback — auto-retries on rate limit or API errors
    llm_with_fallbacks = primary.with_fallbacks(
        [fallback1, fallback2],
        exceptions_to_handle=(Exception,),
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", HUMAN_PROMPT),
        ]
    )

    output_parser = PydanticOutputParser(pydantic_object=RootCauseResult)

    # Chain: prompt → LLM with fallbacks → parse to RootCauseResult
    chain = prompt | llm_with_fallbacks | output_parser

    logger.info(
        "llm.chain_built",
        primary=model_primary,
        fallback1=model_fallback_1,
        fallback2=model_fallback_2,
    )
    return chain


# ---------------------------------------------------------------------------
# Invocation with retry
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False,
)
async def invoke_root_cause(
    chain: RunnableSequence,
    anomaly_context: dict,
    model_id: str = "unknown",
) -> RootCauseResult:
    """
    Invoke the root cause chain with retry.
    On total failure after all retries, returns a safe default result.
    """
    try:
        # Format the context for the prompt
        formatted = {
            "vendor": anomaly_context.get("vendor", "Unknown"),
            "currency": anomaly_context.get("currency", "INR"),
            "amount": float(anomaly_context.get("amount", 0)),
            "category": anomaly_context.get("category", "unknown"),
            "department": anomaly_context.get("department", "unknown"),
            "transaction_date": anomaly_context.get("transaction_date", "unknown"),
            "invoice_number": anomaly_context.get("invoice_number") or "N/A",
            "anomaly_type": anomaly_context.get("anomaly_type", "unknown"),
            "isolation_score": round(float(anomaly_context.get("isolation_score", 0)), 4),
            "rule_flags": ", ".join(anomaly_context.get("rule_flags", [])) or "none",
            "similar_anomalies": _format_similar_anomalies(
                anomaly_context.get("similar_anomalies", [])
            ),
            "model_id": model_id,
        }
        result = await chain.ainvoke(formatted)
        logger.info(
            "llm.root_cause_success",
            model_used=result.model_used,
            confidence=result.confidence,
        )
        return result
    except Exception as exc:
        logger.warning("llm.invoke_failed", error=str(exc))
        raise


def get_default_root_cause_result() -> RootCauseResult:
    """Safe fallback when all LLM calls fail."""
    return RootCauseResult(
        explanation="Automated analysis unavailable. Manual review recommended.",
        confidence=0.0,
        suggested_action="Assign to finance team for manual investigation.",
        model_used="none",
    )


def _format_similar_anomalies(similar: list[dict]) -> str:
    if not similar:
        return "None found."
    lines = []
    for s in similar[:3]:
        lines.append(
            f"- {s.get('vendor', '?')}: {s.get('anomaly_type', '?')} "
            f"({s.get('currency', 'INR')} {s.get('amount', 0):,.0f})"
        )
    return "\n".join(lines)
