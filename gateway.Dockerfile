# Gateway — lightweight, no Blender
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY shared/ /app/shared/
COPY gateway/ /app/gateway/
COPY server.py /app/
COPY index.html /app/
COPY .env.example /app/
RUN mkdir -p /app/output
EXPOSE 8080
ENV PORT=8080 PYTHONUNBUFFERED=1
CMD ["python", "gateway/app.py"]
