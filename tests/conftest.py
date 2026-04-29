import os

os.environ.setdefault("APP_NAME", "async-payments-service")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://payments:payments@localhost:5432/payments")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("PAYMENT_EXCHANGE", "payments")
os.environ.setdefault("PAYMENT_NEW_QUEUE", "payments.new")
os.environ.setdefault("PAYMENT_NEW_ROUTING_KEY", "payments.new")
os.environ.setdefault("PAYMENT_DLX", "payments.dlx")
os.environ.setdefault("PAYMENT_DLQ", "payments.dlq")
os.environ.setdefault("OUTBOX_POLL_INTERVAL_SECONDS", "5")
os.environ.setdefault("WEBHOOK_TIMEOUT_SECONDS", "10")
