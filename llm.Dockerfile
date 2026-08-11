# LLM Service — lightweight, LLM parsing only
# ONLY copies: proto/ (shared types) + llm-service/ (own code)
# Does NOT copy: gateway/, blender-service/, orchestrator/

FROM python:3.12-slim AS builder
WORKDIR /build
COPY llm-service/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY proto/ /app/proto/
COPY shared/ /app/shared/
COPY llm-service/ /app/llm-service/
EXPOSE 8081
ENV PORT=8081 PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "llm-service/app.py"]
