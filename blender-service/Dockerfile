FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    blender \
    python3-pip \
    xvfb \
    locales && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

# Copy shared package (build context = project root)
COPY shared/ ./shared/

# Copy service requirements and install
COPY blender-service/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy service code
COPY blender-service/app.py .

# Legacy: keep promt_parser.py for backward compatibility
COPY promt_parser.py /app/promt_parser.py

RUN mkdir -p /app/output

EXPOSE 8082
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & export DISPLAY=:99 && uvicorn app:app --host 0.0.0.0 --port 8082"]
