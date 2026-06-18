# Alias Dockerfile — build from repo root:
#   docker build -f serving/Dockerfile -t <image> .
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY common/ /app/common/
COPY exporter/ /app/exporter/
COPY model/ /app/model/
COPY serving/ /app/serving/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
