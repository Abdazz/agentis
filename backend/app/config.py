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

    # Search
    search_backend: str = "brave"          # brave|searxng|tavily
    brave_api_key: str = ""
    searxng_url: str = "http://searxng:8080"
    tavily_api_key: str = ""


settings = Settings()
