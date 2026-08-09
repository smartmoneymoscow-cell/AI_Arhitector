# Agent Pool — runs all agents via HTTP
FROM python:3.13-slim AS builder
WORKDIR /build
COPY agent-pool/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY shared/ /app/shared/
COPY agent-pool/ /app/agent-pool/
RUN mkdir -p /app/output
ENV PORT=8083 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8083
CMD ["uvicorn", "agent-pool.app:app", "--host", "0.0.0.0", "--port", "8083"]
