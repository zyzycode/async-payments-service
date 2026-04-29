# async-payments-service

Микросервис асинхронной обработки платежей. Сервис принимает HTTP-запрос на создание платежа, сохраняет его со статусом `pending`, гарантированно публикует событие через outbox, обрабатывает платеж в consumer-е через эмуляцию внешнего платежного шлюза и отправляет результат на `webhook_url`.

## Описание Сервиса

Основной сценарий:

- клиент вызывает `POST /api/v1/payments`;
- сервис возвращает `202 Accepted`;
- платеж обрабатывается асинхронно;
- после обработки клиент получает webhook с итоговым статусом.

Стек:

- FastAPI + Pydantic v2
- SQLAlchemy 2 async
- PostgreSQL
- Alembic
- RabbitMQ + FastStream
- Docker Compose

## Архитектура Ports & Adapters

Проект разделен на слои:

```text
app/
  domain/payments/        # доменные сущности
  application/ports/      # Protocol-интерфейсы
  application/use_cases/  # бизнес-сценарии
  adapters/in_api/        # FastAPI adapter
  adapters/in_consumer/   # FastStream consumer adapter
  adapters/out_db/        # SQLAlchemy adapter
  adapters/out_rabbitmq/  # RabbitMQ publisher adapter
  adapters/out_http/      # payment gateway и webhook HTTP adapters
  core/                   # settings и logging
```

Application layer не импортирует FastAPI, SQLAlchemy, FastStream или httpx напрямую. Инфраструктура подключается через ports.

## Схема Обработки Платежа

1. `POST /api/v1/payments` получает данные платежа и `Idempotency-Key`.
2. `CreatePaymentUseCase` проверяет платеж по `idempotency_key`.
3. Если платеж уже есть, возвращается существующий платеж.
4. Если платежа нет, в одной транзакции создаются:
   - запись в `payments`;
   - запись в `outbox` с событием `payments.new`.
5. `outbox-worker` читает pending outbox events и публикует сообщение в RabbitMQ.
6. `consumer` читает очередь `payments.new`.
7. `ProcessPaymentUseCase` вызывает эмуляцию payment gateway.
8. Статус платежа обновляется в БД.
9. Сервис отправляет webhook клиенту.
10. Если обработка падает, RabbitMQ повторяет доставку. После 3 неуспешных обработок сообщение уходит в DLQ.

## Переменные Окружения

Пример находится в `.env.template`.

```env
APP_NAME=async-payments-service
API_KEY=change-me

POSTGRES_DB=payments
POSTGRES_USER=payments
POSTGRES_PASSWORD=payments
DATABASE_URL=postgresql+asyncpg://payments:payments@postgres:5432/payments

RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

PAYMENT_EXCHANGE=payments
PAYMENT_NEW_QUEUE=payments.new
PAYMENT_NEW_ROUTING_KEY=payments.new
PAYMENT_DLX=payments.dlx
PAYMENT_DLQ=payments.dlq

OUTBOX_POLL_INTERVAL_SECONDS=5
WEBHOOK_TIMEOUT_SECONDS=10
```

## Запуск Через Docker Compose

```bash
cp .env.template .env
docker compose up --build
```

Сервисы:

- API: `http://localhost:8080`
- RabbitMQ Management UI: `http://localhost:15672`
- RabbitMQ credentials: `guest` / `guest`

Внутри compose также запускаются `postgres`, `consumer`, `outbox-worker` и одноразовый сервис `migrate`.
Наружу публикуются только порты `8080` и `15672`; PostgreSQL и AMQP доступны сервисам внутри Docker network.

На чистом окружении при `docker compose up --build` отдельный сервис `migrate` применяет Alembic миграции до старта `api`, `consumer` и `outbox-worker`. Если контейнер `migrate` уже существует и раньше успешно завершился, Docker Compose может не запускать его повторно.

## Применение Миграций

В Docker Compose миграции применяются сервисом `migrate`. На чистом окружении он запускается как часть `docker compose up --build`.

После добавления новых миграций в уже поднятом окружении запустите их явно:

```bash
docker compose run --rm migrate
docker compose up -d --build
```

Локально, если зависимости установлены и `DATABASE_URL` указывает на PostgreSQL:

```bash
alembic upgrade head
```

Если менялись аргументы RabbitMQ очередей, например лимит доставок для DLQ, существующую очередь `payments.new` нужно пересоздать: аргументы очередей в RabbitMQ immutable. В текущем compose у RabbitMQ нет отдельного volume, поэтому `docker compose down` и повторный `docker compose up --build` пересоздают очереди с актуальными аргументами.

Ручной запуск миграций в Docker:

```bash
docker compose run --rm migrate
```

## Pre-commit

В проекте настроены pre-commit hooks:

- `flake8`
- `black`
- `isort`

Установить hooks:

```bash
pre-commit install
```

Запустить проверки вручную:

```bash
pre-commit run --all-files
```

## Примеры curl

Создать платеж:

```bash
curl -i -X POST http://localhost:8080/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -H "Idempotency-Key: payment-demo-001" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Demo payment",
    "metadata": {"order_id": "order-001"},
    "webhook_url": "https://webhook.site/your-url"
  }'
```

Получить платеж:

```bash
curl -i http://localhost:8080/api/v1/payments/<payment_id> \
  -H "X-API-Key: change-me"
```

## Как Проверить Webhook

1. Откройте `https://webhook.site`.
2. Скопируйте уникальный URL.
3. Передайте его в поле `webhook_url` при создании платежа.
4. Дождитесь обработки платежа consumer-ом.
5. На странице webhook.site должен появиться `POST` с payload:

```json
{
  "payment_id": "...",
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "..."
}
```

## Как Проверить RabbitMQ DLQ

1. Запустите сервисы через `docker compose up --build`; миграции применит сервис `migrate`.
2. Откройте RabbitMQ Management UI: `http://localhost:15672`.
3. Перейдите в раздел `Queues`.
4. Найдите очередь `payments.dlq`.
5. Чтобы принудительно проверить DLQ, можно указать недоступный `webhook_url`, например локальный адрес, который не принимает запросы.
6. После 3 неуспешных обработок сообщение должно оказаться в `payments.dlq`.

## Гарантии

- **Idempotency**: повторный `POST` с тем же `Idempotency-Key` возвращает уже созданный платеж и не создает дубль.
- **Outbox**: платеж и событие `payments.new` сохраняются в одной транзакции.
- **Retry**: webhook adapter делает 3 попытки отправки с паузами `1s` и `2s` между попытками; consumer пробрасывает ошибку наружу, чтобы RabbitMQ повторил обработку сообщения.
- **DLQ**: очередь `payments.new` настроена так, чтобы после 3 неуспешных попыток обработки сообщение попадало в `payments.dlq`.
