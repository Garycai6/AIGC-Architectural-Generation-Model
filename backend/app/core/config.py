from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    image_provider: str = "simulator"  # simulator | replicate(默认模拟器,避免空 token 500)
    replicate_api_token: str = ""
    cache_dir: str = ".cache/archgen"
    max_free_quota: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
