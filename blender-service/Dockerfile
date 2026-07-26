FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-numpy blender xvfb \
    libgl1-mesa-glx libxi6 libxrender1 libxxf86vm1 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3 /usr/bin/python
RUN SYS_NUMPY=$(python3 -c "import numpy,os;print(os.path.dirname(numpy.__file__))") && \
    find /usr/share/blender -name "numpy" -type d -exec rm -rf {} + 2>/dev/null; \
    BLENDER_MODULES="/usr/share/blender/scripts/freestyle/modules" && \
    mkdir -p "$BLENDER_MODULES" && cp -r "$SYS_NUMPY" "$BLENDER_MODULES/"
WORKDIR /app
COPY blender-service/requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt
COPY blender-service/ .
RUN mkdir -p output
EXPOSE 8082
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 &>/dev/null & export DISPLAY=:99 && exec python3 app.py"]
