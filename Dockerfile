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

# FIX: Blender bundles broken numpy in freestyle. Remove it and install working one.
# Find Blender's numpy path and replace it.
RUN BLENDER_NUMPY=$(find /usr/share/blender -path "*/freestyle/modules/numpy" -type d 2>/dev/null | head -1) && \
    echo "Blender's broken numpy at: $BLENDER_NUMPY" && \
    if [ -n "$BLENDER_NUMPY" ]; then \
        rm -rf "$BLENDER_NUMPY" && \
        echo "Removed broken numpy"; \
    fi && \
    # Also remove any other bundled numpy
    find /usr/share/blender -name "numpy" -type d -exec rm -rf {} + 2>/dev/null; \
    # Install working numpy into Blender's freestyle/modules (where it expects it)
    pip3 install --break-system-packages numpy --target=/tmp/numpy_pkg && \
    BLENDER_MODULES="/usr/share/blender/scripts/freestyle/modules" && \
    mkdir -p "$BLENDER_MODULES" && \
    cp -r /tmp/numpy_pkg/numpy "$BLENDER_MODULES/" && \
    echo "Installed working numpy to $BLENDER_MODULES" && \
    rm -rf /tmp/numpy_pkg

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8080

CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python3 server.py"]
