# Gateway — API routing + orchestration entry point
# ONLY copies: proto/ (shared types) + gateway/ (own code)
# Does NOT copy: llm-service/, blender-service/, orchestrator/agents/

FROM python:3.11-slim AS builder
WORKDIR /build
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY proto/ /app/proto/
COPY gateway/ /app/gateway/
COPY frontend/ /app/frontend/
RUN mkdir -p /app/output
ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT}"]
