"""
pgvector operations for anomaly similarity search.

Used by Agent 6 (Merge) to:
  1. Generate embeddings for newly merged anomalies
  2. Store them in anomaly_embeddings table
  3. Retrieve similar past anomalies as context for Agent 4 (LLM)

Falls back gracefully if embeddings API is unavailable.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.orm import AnomalyEmbedding

logger = structlog.get_logger(__name__)

# Cached OpenAI async client for embeddings
_embeddings_client: Optional[AsyncOpenAI] = None


def _get_embeddings_client() -> AsyncOpenAI:
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "dummy-key")
        )
    return _embeddings_client


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


async def embed_text(text_input: str) -> Optional[list[float]]:
    """
    Generate a text embedding vector using OpenAI's embedding model.
    Returns None if the API call fails (graceful degradation).
    """
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    try:
        client = _get_embeddings_client()
        response = await client.embeddings.create(
            model=model,
            input=text_input[:8000],  # Truncate to avoid token limit
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("vector_store.embed_failed", error=str(exc))
        return None


def build_anomaly_source_text(anomaly_data: dict) -> str:
    """
    Build the text string used to generate the embedding for an anomaly.
    Combines the most semantically meaningful fields.
    """
    parts = [
        f"Vendor: {anomaly_data.get('vendor', 'unknown')}",
        f"Category: {anomaly_data.get('category', 'unknown')}",
        f"Type: {anomaly_data.get('anomaly_type', 'unknown')}",
        f"Department: {anomaly_data.get('department', 'unknown')}",
        f"Amount: {anomaly_data.get('currency', 'INR')} {anomaly_data.get('amount', 0):,.0f}",
    ]
    if anomaly_data.get("root_cause"):
        parts.append(f"Root cause: {anomaly_data['root_cause']}")
    if anomaly_data.get("rule_flags"):
        flags = anomaly_data["rule_flags"]
        if isinstance(flags, list):
            parts.append(f"Flags: {', '.join(flags)}")
    return ". ".join(parts)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


async def store_anomaly_embedding(
    session: AsyncSession,
    anomaly_id: str,
    anomaly_data: dict,
) -> Optional[AnomalyEmbedding]:
    """
    Generate and store an embedding for a merged anomaly.
    Silently skips if embedding generation fails.
    """
    source_text = build_anomaly_source_text(anomaly_data)
    embedding_vector = await embed_text(source_text)

    if embedding_vector is None:
        logger.debug("vector_store.skip_store", anomaly_id=anomaly_id, reason="embed_failed")
        return None

    row = AnomalyEmbedding(
        anomaly_id=anomaly_id,
        embedding=embedding_vector,
        source_text=source_text,
    )
    session.add(row)
    try:
        await session.commit()
        await session.refresh(row)
        logger.debug("vector_store.stored", anomaly_id=anomaly_id)
        return row
    except Exception as exc:
        await session.rollback()
        logger.warning("vector_store.store_failed", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------


async def find_similar_anomalies(
    session: AsyncSession,
    query_text: str,
    top_k: int = 3,
    similarity_threshold: float = 0.75,
) -> list[dict]:
    """
    Find anomalies similar to the query text using cosine similarity.
    Returns a list of dicts with anomaly_id and similarity score.
    Falls back to empty list if search fails.
    """
    embedding = await embed_text(query_text)
    if embedding is None:
        return []

    try:
        # pgvector cosine similarity query
        # <=> operator = cosine distance; similarity = 1 - distance
        result = await session.execute(
            text(
                """
                SELECT ae.anomaly_id, ae.source_text,
                       1 - (ae.embedding <=> cast(:embedding as vector)) AS similarity
                FROM anomaly_embeddings ae
                WHERE 1 - (ae.embedding <=> cast(:embedding as vector)) > :threshold
                ORDER BY ae.embedding <=> cast(:embedding as vector)
                LIMIT :top_k
                """
            ),
            {
                "embedding": str(embedding),
                "threshold": similarity_threshold,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        return [
            {"anomaly_id": row.anomaly_id, "source_text": row.source_text, "similarity": row.similarity}
            for row in rows
        ]
    except Exception as exc:
        logger.warning("vector_store.search_failed", error=str(exc))
        return []
