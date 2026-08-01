FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends locales && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONIOENCODING=utf-8
ENV PORT=8080

WORKDIR /app

COPY shared/ ./shared/
COPY gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway/ .
COPY frontend/ ./frontend/

EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
