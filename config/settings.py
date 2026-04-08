from pydantic_settings import BaseSettings, SettingsConfigDict

from config.defaults import (
    APP_ENV,
    APP_NAME,
    DEFAULT_PERSONA_DESCRIPTION,
    DEFAULT_PERSONA_NAME,
    DEFAULT_PERSONA_RULES,
    DEFAULT_PERSONA_STYLE,
    ENABLE_MOCK_LLM,
    LLM_MODEL,
    LLM_PROVIDER,
    LOG_LEVEL,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = APP_NAME
    app_env: str = APP_ENV
    log_level: str = LOG_LEVEL

    llm_provider: str = LLM_PROVIDER
    llm_model: str = LLM_MODEL
    enable_mock_llm: bool = ENABLE_MOCK_LLM

    openai_api_key: str | None = None
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    persona_name: str = DEFAULT_PERSONA_NAME
    persona_description: str = DEFAULT_PERSONA_DESCRIPTION
    persona_style: str = DEFAULT_PERSONA_STYLE
    persona_rules: str = DEFAULT_PERSONA_RULES


settings = Settings()
