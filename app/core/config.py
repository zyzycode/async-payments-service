from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "async-payments-service"
    app_version: str = "0.1.0"
    debug: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "payments"
    postgres_user: str = "payments"
    postgres_password: str = "payments"

    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"

    database_url: str | None = Field(default=None)
    rabbitmq_url: str | None = Field(default=None)

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            "postgresql+asyncpg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def rabbit_url(self) -> str:
        if self.rabbitmq_url:
            return self.rabbitmq_url
        return "amqp://" f"{self.rabbitmq_user}:{self.rabbitmq_password}" f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"


settings = Settings()
