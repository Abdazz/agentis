FROM python:3.12-slim

WORKDIR /app

RUN pip install hatch

COPY pyproject.toml .
RUN pip install -e ".[voice]"

# Pre-warm the tiktoken BPE cache at build time so the API never needs
# network egress to openaipublic.blob.core.windows.net at runtime/startup.
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
