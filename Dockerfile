FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["/bin/sh", "-c", "gunicorn webhook:app --workers 2 --bind 0.0.0.0:$PORT --timeout 60"]
