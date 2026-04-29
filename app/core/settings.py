from pydantic import Field, PositiveFloat, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(validation_alias="APP_NAME")
    api_key: SecretStr = Field(validation_alias="API_KEY")
    database_url: str = Field(validation_alias="DATABASE_URL")
    rabbitmq_url: str = Field(validation_alias="RABBITMQ_URL")

    payment_exchange: str = Field(validation_alias="PAYMENT_EXCHANGE")
    payment_new_queue: str = Field(validation_alias="PAYMENT_NEW_QUEUE")
    payment_new_routing_key: str = Field(validation_alias="PAYMENT_NEW_ROUTING_KEY")
    payment_dlx: str = Field(validation_alias="PAYMENT_DLX")
    payment_dlq: str = Field(validation_alias="PAYMENT_DLQ")

    outbox_poll_interval_seconds: PositiveFloat = Field(
        validation_alias="OUTBOX_POLL_INTERVAL_SECONDS",
    )
    webhook_timeout_seconds: PositiveFloat = Field(
        validation_alias="WEBHOOK_TIMEOUT_SECONDS",
    )


settings = Settings()
