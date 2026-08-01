# Blender Service — heavy, Blender + Xvfb
FROM debian:bookworm-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-numpy \
    blender xvfb libgl1-mesa-glx libxi6 libxrender1 libxxf86vm1 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3 /usr/bin/python
RUN find /usr/share/blender -name "numpy" -type d -exec rm -rf {} + 2>/dev/null; \
    SYS_NUMPY=$(python3 -c "import numpy; import os; print(os.path.dirname(numpy.__file__))") && \
    BLENDER_MODULES="/usr/share/blender/scripts/freestyle/modules" && \
    mkdir -p "$BLENDER_MODULES" && cp -r "$SYS_NUMPY" "$BLENDER_MODULES/"
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt
COPY shared/ /app/shared/
COPY blender-service/ /app/blender-service/
COPY server.py /app/
RUN mkdir -p /app/output
EXPOSE 8082
ENV PORT=8082 DISPLAY=:99 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 &>/dev/null & exec python3 blender-service/app.py"]
