FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium --with-deps

COPY tool_server/ ./sandbox/tool_server/
RUN touch ./sandbox/__init__.py ./sandbox/tool_server/__init__.py

RUN mkdir -p /workspace/inputs /workspace/outputs && chmod 777 /workspace

RUN useradd -m -u 1000 sandbox && chown -R sandbox:sandbox /workspace
USER sandbox

EXPOSE 9999

CMD ["uvicorn", "sandbox.tool_server.main:app", "--host", "0.0.0.0", "--port", "9999"]
