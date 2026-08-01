# LLM Service — lightweight, no Blender
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
# Force fresh copy of shared (no Docker cache)
ARG CACHEBUST=$(date +%s)
RUN echo "Cache bust $CACHEBUST"
COPY shared/ /app/shared/
COPY llm-service/ /app/llm-service/
EXPOSE 8081
ENV PORT=8081 PYTHONUNBUFFERED=1
CMD ["python", "llm-service/app.py"]
