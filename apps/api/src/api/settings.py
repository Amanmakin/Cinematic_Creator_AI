from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_path: str = "projects.sqlite"
    openai_api_key: str = ""
    replicate_api_key: str = ""
    uar_root: str = "uar_assets"
    cors_origins: list[str] = ["http://localhost:3000"]
    ws_ping_interval: int = 20


settings = Settings()
