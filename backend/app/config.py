from urllib.parse import urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIS_", env_file=".env")

    # Database
    database_url: PostgresDsn = "postgresql+asyncpg://agentis:agentis@pgbouncer:5432/agentis"
    postgres_direct_url: PostgresDsn = "postgresql+asyncpg://agentis:agentis@postgres:5432/agentis"

    # Redis
    redis_broker_url: str = "redis://redis:6379/0"
    redis_cache_url: str = "redis://redis:6379/1"

    # Auth
    jwt_private_key_path: str = "/secrets/jwt/private.pem"
    jwt_public_key_path: str = "/secrets/jwt/public.pem"
    jwt_access_ttl: int = 3600
    jwt_refresh_ttl: int = 2592000

    # Rate limits
    rate_limit_task_hour: int = 60
    rate_limit_api_hour: int = 1000

    # App
    default_language: str = "fr"
    log_level: str = "INFO"
    environment: str = "development"

    # Sandbox
    sandbox_image: str = "agentis-sandbox:latest"
    sandbox_max_concurrent: int = 10
    sandbox_warm_pool_size: int = 2
    sandbox_timeout_seconds: int = 1800
    sandbox_network: str = "agentis_default"  # Docker network name
    sandbox_rpc_port: int = 9999
    egress_proxy_url: str = ""  # e.g. http://squid:3128 (empty = no proxy)

    # Tools
    tool_output_max_tokens: int = 8000
    code_executor_timeout_s: int = 120
    mcp_timeout_s: int = 30

    # Search
    search_backend: str = "brave"          # brave|searxng|tavily
    brave_api_key: str = ""
    searxng_url: str = "http://searxng:8080"
    tavily_api_key: str = ""

    # LLM
    llm_provider: str = "anthropic"        # anthropic|openai|mistral|groq|deepseek|ollama
    llm_model: str = "claude-sonnet-4-5-20251022"
    llm_api_key: str = ""
    llm_base_url: str = ""                  # Ollama / self-hosted
    llm_timeout_s: int = 120
    context_budget: float = 0.8             # fraction of model window before summarize
    memory_injection_tokens: int = 2000

    # Token budgets
    token_budget_per_task: int = 100000
    token_budget_user_monthly: int = 2000000

    # Agent behavior
    default_max_iterations: int = 30
    max_iterations_cap: int = 50
    hitl_confidence_threshold: float = 0.3
    hitl_timeout_seconds: int = 3600
    worker_concurrency: int = 4
    max_total_failures: int = 10

    # Observability
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    prometheus_enabled: bool = True
    loki_url: str = ""
    loki_app_name: str = "agentis-backend"

    # Qdrant (long-term memory)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "agentis_memory"

    # Voyage AI (embeddings)
    voyage_api_key: str = ""
    voyage_model: str = "voyage-multilingual-2"
    voyage_embedding_dim: int = 1024
    voyage_base_url: str = ""  # e.g. http://voyage-server:8080/v1 for self-hosted

    # MinIO / S3
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "agentis"
    minio_secret_key: str = "agentis123"
    minio_secure: bool = False
    minio_bucket_uploads: str = "agentis-uploads"
    minio_bucket_artifacts: str = "agentis-artifacts"
    minio_bucket_backups: str = "agentis-backups"
    minio_presigned_expiry_seconds: int = 3600

    # HTTP Caller (safe domains — comma-separated, no spaces)
    http_caller_safe_domains: str = ""

    # Webhook security
    fernet_key: str = ""  # Set in production: Fernet.generate_key().decode()

    # ClamAV file scanning (Phase 3B)
    clamav_socket: str = "/var/run/clamav/clamd.ctl"
    clamav_enabled: bool = False

    # Voice services (Phase 4B)
    whisper_model: str = "base"   # tiny, base, small, medium, large
    whisper_device: str = "cpu"   # cpu or cuda
    tts_voice: str = "fr-FR-DeniseNeural"

    @property
    def http_caller_safe_domain_set(self) -> set[str]:
        if not self.http_caller_safe_domains:
            return set()
        normalized = self.http_caller_safe_domains.replace("\r\n", ",").replace("\n", ",")
        return {d.strip() for d in normalized.split(",") if d.strip()}

    @property
    def checkpointer_dsn(self) -> str:
        """psycopg DSN for the LangGraph checkpointer (direct Postgres, ADR-1C-01).

        Strips any ``postgresql+<driver>://`` scheme down to plain
        ``postgresql://`` so psycopg (sync) accepts the URL regardless of
        which async driver variant is stored in ``postgres_direct_url``.
        """
        parsed = urlparse(str(self.postgres_direct_url))
        return urlunparse(parsed._replace(scheme="postgresql"))


settings = Settings()
