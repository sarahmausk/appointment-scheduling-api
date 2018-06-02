from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/appointments"
    secret_key: str = "change-me-to-a-long-random-secret"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"


settings = Settings()
