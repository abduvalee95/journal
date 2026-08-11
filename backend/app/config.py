from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bot_token: str
    webhook_secret: str
    teacher_telegram_id: int
    base_url: str
    miniapp_url: str
    jwt_secret: str
    database_url: str = "sqlite+aiosqlite:///./data/journal.db"
    elevenlabs_api_key: str
    llm_api_key: str
    llm_model: str = "claude-haiku-4-5-20251001"

    class Config:
        env_file = ".env"

settings = Settings()
