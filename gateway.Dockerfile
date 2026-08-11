# Gateway — API routing + orchestration entry point
# ONLY copies: proto/ (shared types) + gateway/ (own code)
# Does NOT copy: llm-service/, blender-service/, orchestrator/agents/

FROM python:3.12-slim AS builder
WORKDIR /build
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY proto/ /app/proto/
COPY shared/ /app/shared/
COPY gateway/ /app/gateway/
COPY frontend/ /app/frontend/
# FIX: root index.html (1823 lines) is the actively developed frontend —
# it has PDF/DWG upload+analyze (analyzeUploadedFile -> /api/v1/analyze/pdf,
# /api/v1/analyze/dwg) which the gateway backend already supports, but the
# stale frontend/index.html (1696 lines) that used to be shipped never
# called those routes at all. Overwrite it so the deployed frontend matches
# what the backend actually offers. compliance-panel.html / demo_compliance.html
# in frontend/ are left as-is.
COPY index.html /app/frontend/index.html
RUN mkdir -p /app/output
ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT}"]
