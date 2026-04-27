# async-payments-service

FastAPI payment microservice skeleton using Ports & Adapters.

## Stack

- FastAPI
- Pydantic v2
- SQLAlchemy 2 async
- PostgreSQL
- Alembic
- FastStream RabbitMQ
- Docker Compose

## Structure

```text
app/
  domain/payments/        # domain entities and value objects
  application/ports/      # interfaces required by use cases
  application/use_cases/  # application scenarios
  adapters/in_api/        # inbound HTTP adapter
  adapters/in_consumer/   # inbound RabbitMQ consumers
  adapters/out_db/        # SQLAlchemy persistence adapter
  adapters/out_rabbitmq/  # RabbitMQ publishing adapter
  adapters/out_http/      # outbound HTTP adapter
  core/                   # settings and shared configuration
  main.py                 # FastAPI entrypoint
  consumer.py             # FastStream entrypoint
```

## Local Run

```bash
cp .env.template .env
docker compose up --build
```

API healthcheck:

```bash
curl http://localhost:8000/health
```

RabbitMQ management UI:

```text
http://localhost:15672
```

Default credentials are `guest` / `guest`.

## Pre-commit

The project uses pre-commit hooks for basic code quality checks:

- `flake8`
- `black`
- `isort`

Install pre-commit and enable hooks:

```bash
pip install pre-commit
pre-commit install
```

Run checks manually for all files:

```bash
pre-commit run --all-files
```

## Migrations

Create a migration:

```bash
alembic revision --autogenerate -m "init payments"
```

Apply migrations:

```bash
alembic upgrade head
```
