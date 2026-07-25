FROM debian:bookworm-slim

# Install Python + Blender + display libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    blender \
    xvfb \
    libgl1-mesa-glx \
    libxi6 \
    libxrender1 \
    libxxf86vm1 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

# Symlink python
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Install numpy into Blender's Python modules path
RUN pip3 install --break-system-packages numpy --target=/tmp/numpy_pkg && \
    BLENDER_MODULES=$(find /usr/share/blender -name "modules" -type d 2>/dev/null | head -1) && \
    echo "Blender modules dir: $BLENDER_MODULES" && \
    if [ -n "$BLENDER_MODULES" ]; then \
        cp -r /tmp/numpy_pkg/numpy "$BLENDER_MODULES/"; \
    fi && \
    rm -rf /tmp/numpy_pkg

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8080

CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python3 server.py"]
