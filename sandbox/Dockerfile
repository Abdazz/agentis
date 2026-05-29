FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    nodejs \
    npm \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /workspace/inputs /workspace/outputs && chmod 777 /workspace

RUN useradd -m -u 1000 sandbox && chown -R sandbox:sandbox /workspace

COPY tool_server/ ./sandbox/tool_server/
RUN touch ./sandbox/__init__.py ./sandbox/tool_server/__init__.py

# Install Playwright browsers as root
RUN playwright install chromium --with-deps

# Copy browser cache to /app/.cache so it's accessible from non-root user
RUN mkdir -p /app/.cache && \
    cp -r /root/.cache/ms-playwright /app/.cache/ && \
    chmod -R 755 /app/.cache && \
    chown -R sandbox:sandbox /app/.cache

# Set PLAYWRIGHT_BROWSERS_PATH for the sandbox user
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

USER sandbox

EXPOSE 9999

CMD ["uvicorn", "sandbox.tool_server.main:app", "--host", "0.0.0.0", "--port", "9999"]
