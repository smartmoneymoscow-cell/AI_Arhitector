FROM debian:bookworm-slim

# Install Python + Blender + numpy + display libs
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

# Remove Blender's broken bundled numpy, replace with system numpy
RUN echo "--- Cleaning Blender numpy ---" && \
    find /usr/share/blender -name "numpy" -type d 2>/dev/null && \
    find /usr/share/blender -name "numpy" -type d -exec rm -rf {} + 2>/dev/null; \
    echo "--- Copying system numpy ---" && \
    SYS_NUMPY=$(python3 -c "import numpy; import os; print(os.path.dirname(numpy.__file__))") && \
    echo "System numpy at: $SYS_NUMPY" && \
    BLENDER_MODULES="/usr/share/blender/scripts/freestyle/modules" && \
    mkdir -p "$BLENDER_MODULES" && \
    cp -r "$SYS_NUMPY" "$BLENDER_MODULES/" && \
    echo "Copied numpy to $BLENDER_MODULES" && \
    python3 -c "import sys; sys.path.insert(0,'$BLENDER_MODULES'); import numpy; print('OK:', numpy.__version__)"

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8080

CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python3 server.py"]
