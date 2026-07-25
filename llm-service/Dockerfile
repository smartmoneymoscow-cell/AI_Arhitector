FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir flask flask-cors httpx
ENV PYTHONUNBUFFERED=1
EXPOSE 8081
CMD ["python", "-X", "utf8", "app.py"]
