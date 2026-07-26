FROM python:3.11-slim
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir flask flask-cors requests
EXPOSE 8081
CMD ["python", "-X", "utf8", "app.py"]
