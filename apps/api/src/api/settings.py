from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_path: str = "projects.sqlite"
    openai_api_key: str = ""
    replicate_api_key: str = ""
    uar_root: str = "uar_assets"
    cors_origins: list[str] = ["http://localhost:3000"]
    ws_ping_interval: int = 20
    redis_url: str = "redis://localhost:6379"
    renders_root: str = "renders"

    # LLM settings (overridable at runtime via /llm-settings endpoint)
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""

    # Plan8: Hybrid adapter / Docker diffusers settings
    generation_strategy: str = "local_fallback"
    """local_only | local_fallback | replicate_only | replicate_fallback"""
    docker_diffusers_url: str = "http://localhost:8001"
    """Local Docker diffusers service endpoint"""
    generation_timeout_local: int = 180
    """Timeout for local inference (seconds). M4 Air SDXL ~120-300s"""
    generation_timeout_replicate: int = 120
    """Timeout for Replicate API calls (seconds)"""
    use_smaller_models_locally: bool = True
    """Use SD1.5 instead of SDXL on Mac/CPU (faster, lower quality)"""


settings = Settings()
