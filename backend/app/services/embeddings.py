"""Embeddings for the memory layer. Live = OpenAI text-embedding-3-large at
1536 dims (resolves the blueprint's dimension mismatch). Mock = deterministic
hash-based vector so similarity search still works offline."""
from __future__ import annotations

import hashlib
import math

from ..config import settings

_LIVE = bool(settings.openai_api_key)
DIMS = settings.embedding_dims


async def embed(text: str) -> list[float]:
    if not _LIVE:
        return _mock_embed(text)
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=DIMS,  # request reduced dims to match vector(1536)
    )
    return resp.data[0].embedding


def _mock_embed(text: str) -> list[float]:
    """Hash words into a fixed-dim L2-normalized vector. Same text → same vector,
    similar text → overlapping dimensions, so cosine similarity is meaningful."""
    vec = [0.0] * DIMS
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % DIMS] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
