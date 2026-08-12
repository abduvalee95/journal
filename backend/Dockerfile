FROM python:3.12-slim

# Unbuffered so container logs appear as they happen rather than in blocks;
# no .pyc files since the layer is read-only in practice.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. The uid is fixed so the ./data bind mount can be
# chowned to a matching owner on the host (see docs/deploy.md).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# One worker, deliberately. The outbox loop and the Telegram webhook
# registration both live in the FastAPI lifespan, so a second worker would
# start a second outbox and send every student their report twice.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
