"""
Self-hosted Reranker Service (Cohere-compatible API)
Model: BAAI/bge-reranker-v2-m3

This service provides a Cohere-compatible /rerank endpoint
that can be used with LightRAG's RERANK_BINDING=cohere setting.
"""

import os
import time
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reranker")

# Model configuration
MODEL_NAME = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MAX_LENGTH = int(os.getenv("MAX_LENGTH", "512"))

# Global model instance
model: CrossEncoder = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown."""
    global model
    logger.info(f"Loading reranker model: {MODEL_NAME}")
    start = time.time()
    
    try:
        model = CrossEncoder(MODEL_NAME, max_length=MAX_LENGTH)
        load_time = time.time() - start
        logger.info(f"Model loaded successfully in {load_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise
    
    yield
    
    # Cleanup
    logger.info("Shutting down reranker service")


app = FastAPI(
    title="Reranker Service",
    description="Cohere-compatible reranking API using BAAI/bge-reranker-v2-m3",
    version="1.0.0",
    lifespan=lifespan
)


# Cohere-compatible request/response models
class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_n: Optional[int] = None
    model: Optional[str] = None  # Ignored, we use our loaded model
    return_documents: Optional[bool] = False


class RerankResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[str] = None


class RerankResponse(BaseModel):
    results: List[RerankResult]
    meta: dict = {}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": MODEL_NAME,
        "loaded": model is not None
    }


@app.post("/v1/rerank", response_model=RerankResponse)
@app.post("/v2/rerank", response_model=RerankResponse)  # Cohere v2 compatibility
@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """
    Rerank documents based on relevance to query.
    
    Cohere-compatible endpoint that can be used with LightRAG.
    OPTIMIZATION: Limits documents to MAX_DOCS for CPU performance.
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.documents:
        return RerankResponse(results=[], meta={"model": MODEL_NAME})
    
    start_time = time.time()
    
    # OPTIMIZATION: Limit documents for CPU performance
    # If too many docs, take first MAX_DOCS (assumes pre-sorted by vector similarity)
    MAX_DOCS = 30  # Reasonable limit for CPU
    original_count = len(request.documents)
    documents = request.documents[:MAX_DOCS] if len(request.documents) > MAX_DOCS else request.documents
    
    try:
        # Create query-document pairs for scoring
        pairs = [[request.query, doc] for doc in documents]
        
        # Get relevance scores (batch_size for memory efficiency)
        scores = model.predict(pairs, show_progress_bar=False, batch_size=8)
        
        # Create results with index and score
        results = [
            {"index": i, "score": float(score)}
            for i, score in enumerate(scores)
        ]
        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # Apply top_n limit
        top_n = request.top_n or 10
        results = results[:top_n]
        
        # Format response (Cohere-compatible)
        formatted_results = []
        for r in results:
            result = RerankResult(
                index=r["index"],
                relevance_score=r["score"]
            )
            if request.return_documents:
                result.document = documents[r["index"]]
            formatted_results.append(result)
        
        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"Reranked {len(documents)} docs (from {original_count}) in {latency_ms:.1f}ms")
        
        return RerankResponse(
            results=formatted_results,
            meta={
                "model": MODEL_NAME,
                "latency_ms": round(latency_ms, 1),
                "documents_processed": len(documents),
                "documents_received": original_count,
                "documents_limited": original_count > MAX_DOCS
            }
        )
        
    except Exception as e:
        logger.error(f"Reranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

