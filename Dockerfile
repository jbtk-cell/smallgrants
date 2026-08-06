# Serving image. Expects a packaged corpus (`smallgrants package`) mounted or
# copied to /data: smallgrants.duckdb, cause_embeddings.npy, cause_embeddings_eins.txt.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SMALLGRANTS_DATA=/data \
    HF_HOME=/opt/hf \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

# CPU-only torch. The GPU build is several GB and buys nothing here.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir .

# Bake the embedding model into the image so the container never reaches out to
# Hugging Face at request time, and never fails because the Hub is rate limiting.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "smallgrants.app:app", "--host", "0.0.0.0", "--port", "8000"]
