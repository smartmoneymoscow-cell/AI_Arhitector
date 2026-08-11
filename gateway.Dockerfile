# Gateway — API routing + orchestration entry point
# ONLY copies: proto/ (shared types) + gateway/ (own code)
# Does NOT copy: llm-service/, blender-service/, orchestrator/agents/

FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends libgeos-dev && rm -rf /var/lib/apt/lists/*
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgeos3 libgeos-c1v5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY proto/ /app/proto/
COPY shared/ /app/shared/
COPY gateway/ /app/gateway/
COPY frontend/ /app/frontend/
COPY index.html /app/frontend/index.html
RUN mkdir -p /app/output
ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT}"]
