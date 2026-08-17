# Hugging Face Space, Docker SDK. Spaces run as uid 1000 and expose port 7860.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface \
    SMALLGRANTS_DATA=/home/user/data \
    SMALLGRANTS_TRUST_PROXY=1

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user pyproject.toml README.md ./
COPY --chown=user src ./src

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir . huggingface_hub

USER user

# Bake the embedding model in so a cold start never waits on the Hub, and a Hub
# outage or rate limit cannot take the site down.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY --chown=user deploy/hf/start.py ./start.py

EXPOSE 7860
CMD ["python", "start.py"]
