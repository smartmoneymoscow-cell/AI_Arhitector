FROM python:3.11-slim

# Install Blender + Xvfb + display libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    blender \
    xvfb \
    libgl1-mesa-glx \
    libxi6 \
    libxrender1 \
    libxxf86vm1 \
    && rm -rf /var/lib/apt/lists/*

# Blender uses its own bundled Python. Find its modules path and install numpy there.
# On Debian, Blender scripts live at /usr/share/blender/scripts/modules/
RUN pip install numpy --target=/tmp/numpy_pkg && \
    BLENDER_MODULES=$(find /usr/share/blender -name "modules" -type d 2>/dev/null | head -1) && \
    if [ -n "$BLENDER_MODULES" ]; then \
        cp -r /tmp/numpy_pkg/numpy "$BLENDER_MODULES/"; \
        echo "Installed numpy to $BLENDER_MODULES"; \
    else \
        echo "WARNING: Blender modules dir not found, installing to scripts/modules"; \
        mkdir -p /usr/share/blender/scripts/modules && \
        cp -r /tmp/numpy_pkg/numpy /usr/share/blender/scripts/modules/; \
    fi && \
    rm -rf /tmp/numpy_pkg

# Verify Blender + numpy
RUN blender --background --factory-startup --python-expr "import numpy; print('numpy OK:', numpy.__version__)" 2>&1 | grep -E "numpy OK|Error"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8080

# Xvfb for headless Blender + Flask server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python server.py"]
