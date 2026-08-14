from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    webhook_secret: str = ""
    teacher_telegram_id: int
    base_url: str = ""
    miniapp_url: str = ""
    jwt_secret: str
    database_url: str = "sqlite+aiosqlite:///./data/journal.db"
    elevenlabs_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"

    model_config = SettingsConfigDict(env_file=[".env", "../.env"], extra="ignore")

settings = Settings()
