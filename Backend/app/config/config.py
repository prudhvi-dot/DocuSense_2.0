from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    OPENAI_API_KEY: str
    DATABASE_URL: str
    LANGCHAIN_TRACING_V2: bool
    LANGCHAIN_ENDPOINT: str
    LANGCHAIN_API_KEY: str
    LANGCHAIN_PROJECT: str
    TAVILY_API_KEY: str
    PINECONE_API_KEY: str
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 90
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str


settings = Settings()
