FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    chainlit==2.9.3 \
    httpx \
    psycopg2-binary \
    sqlalchemy \
    asyncpg

COPY app.py .
COPY chainlit.md .
COPY config.toml .
COPY public ./public
COPY chainlit_patch.py .

# Apply the patch to fix Chainlit 2.9.3 showInput boolean bug
RUN python chainlit_patch.py

# Copy custom config to disable file uploads (query-only interface)
RUN mkdir -p /app/.chainlit && cp config.toml /app/.chainlit/config.toml

EXPOSE 8000

CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
