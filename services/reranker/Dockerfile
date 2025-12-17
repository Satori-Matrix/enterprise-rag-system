# Reranker Service Dockerfile
# Model: BAAI/bge-reranker-v2-m3 (~568MB)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
# Using CPU-only torch to save space
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download the model during build (faster startup)
# Using ms-marco-MiniLM-L-6-v2 (fastest on CPU, ~80MB)
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application
COPY app.py .

# Environment variables
ENV PORT=8080
ENV RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENV MAX_LENGTH=512

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "app.py"]

