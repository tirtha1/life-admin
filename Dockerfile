FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./

# Install all production dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" \
    "sqlalchemy[asyncio]>=2.0" asyncpg \
    "confluent-kafka>=2.4" \
    "anthropic>=0.43" \
    "langgraph>=0.2" \
    hvac \
    "opentelemetry-sdk>=1.27" "opentelemetry-exporter-otlp>=1.27" \
    "opentelemetry-instrumentation-fastapi>=0.48b0" \
    "opentelemetry-instrumentation-sqlalchemy>=0.48b0" \
    "redis>=5.0" "celery>=5.4" \
    boto3 \
    google-auth google-auth-oauthlib google-api-python-client \
    html2text bleach \
    pandas pdfplumber "python-dateutil>=2.9" "pydantic-settings>=2.6" python-multipart \
    tenacity "structlog>=24.4" \
    sendgrid twilio \
    jinja2 \
    pydantic "pyjwt>=2.8" \
    "python-jose[cryptography]"

COPY . .

# The CMD is overridden per service in docker-compose.yml
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
