from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn


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


settings = Settings()
