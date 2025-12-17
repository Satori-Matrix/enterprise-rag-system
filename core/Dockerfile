FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir raganything[all]
RUN pip install --no-cache-dir PyJWT fastapi uvicorn httpx psycopg2-binary

COPY . .

RUN mkdir -p /app/inputs /app/rag_storage /app/output

# PATCH 1: ollama.py - timeout fix
RUN sed -i 's/timeout = kwargs.pop("timeout", None)/timeout = kwargs.pop("timeout", 600)/' \
    /usr/local/lib/python3.11/site-packages/lightrag/llm/ollama.py 2>/dev/null || true

# PATCH 2: prompt.py - prevent entity hallucination
RUN sed -i 's/PROMPTS\["entity_extraction_user_prompt"\] = """---Task---/PROMPTS["entity_extraction_user_prompt"] = """---Task---\nIMPORTANT: Extract entities from the REAL INPUT TEXT below ONLY. Do NOT generate example data like Apple, Tim Cook, or John Doe. Extract actual entities from the provided text./' \
    /usr/local/lib/python3.11/site-packages/lightrag/prompt.py 2>/dev/null || true

EXPOSE 9621

CMD ["python", "/app/server.py"]
