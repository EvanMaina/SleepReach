FROM python:3.11.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

FROM python:3.11.11-slim as production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN groupadd -r sleepreach && useradd -r -g sleepreach sleepreach
RUN mkdir -p /var/run/celery && chown sleepreach:sleepreach /var/run/celery
COPY --chown=sleepreach:sleepreach src/ /app/src/
COPY --chown=sleepreach:sleepreach static/ /app/static/
COPY --chown=sleepreach:sleepreach scripts/ /app/scripts/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
USER sleepreach
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM production as development
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx black isort mypy flake8
USER sleepreach
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--proxy-headers", "--forwarded-allow-ips", "*"]
