FROM debian:bookworm-slim

# Install Python + Blender + display libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-numpy \
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

# Remove Blender's bundled numpy, replace with system numpy
RUN find /usr/share/blender -name "numpy" -type d -exec rm -rf {} + 2>/dev/null; \
    SYS_NUMPY=$(python3 -c "import numpy; import os; print(os.path.dirname(numpy.__file__))") && \
    BLENDER_MODULES="/usr/share/blender/scripts/freestyle/modules" && \
    mkdir -p "$BLENDER_MODULES" && \
    cp -r "$SYS_NUMPY" "$BLENDER_MODULES/"

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .

RUN mkdir -p /app/output

# Default: start Xvfb + server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 &>/dev/null & export DISPLAY=:99 && exec python3 server.py"]
