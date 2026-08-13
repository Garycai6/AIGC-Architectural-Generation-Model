from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    image_provider: str = "simulator"  # simulator | replicate(默认模拟器,避免空 token 500)
    replicate_api_token: str = ""
    sdxl_model: str = ""  # 带 LoRA 的模型名,空=用默认 SDXL_MODEL
    lora_weights_dir: str = ""  # 风格 LoRA 权重公网 URL 目录,空=不注入
    cache_dir: str = ".cache/archgen"
    max_free_quota: int = 5
    quota_storage_path: str = ""  # quota 持久化 JSON 文件路径,空=内存模式(重启清零)


@lru_cache
def get_settings() -> Settings:
    return Settings()
