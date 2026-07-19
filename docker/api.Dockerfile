FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY globalroamer_platform ./globalroamer_platform
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install .

EXPOSE 8000

CMD [
    "uvicorn",
    "globalroamer_platform.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]
