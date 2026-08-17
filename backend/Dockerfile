# Pinned to a digest, not a floating tag: `python:3.12-slim` a month from now
# is a different image, and nothing else in this build records which one was
# tested. Dependabot keeps the digest current (see .github/dependabot.yml).
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS builder

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY requirements.txt .
# Installed into a prefix so only the packages themselves cross into the final
# image -- the pip cache and any build toolchain stay behind.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

# Unbuffered so container logs appear as they happen rather than in blocks;
# no .pyc files since the layer is read-only in practice.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /install /usr/local

# .dockerignore keeps tests/, requirements-dev.txt, .env and the live database
# out of the image. alembic/ is deliberately included: deploy runs
# `alembic upgrade head` inside the container.
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
