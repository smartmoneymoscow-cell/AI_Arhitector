FROM python:3.11-slim

# Install Blender + Xvfb + system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    blender \
    xvfb \
    libgl1-mesa-glx \
    libxi6 \
    libxrender1 \
    libxxf86vm1 \
    && rm -rf /var/lib/apt/lists/*

# Blender's glTF exporter needs numpy
RUN pip install --no-cache-dir numpy

# Verify Blender
RUN blender --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8080

# Xvfb for headless Blender + Flask server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python server.py"]
