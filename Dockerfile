# Dockerfile
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System-Dependencies für WeasyPrint (PDF) + Fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 libglib2.0-0 \
    libffi7 || true && \
    apt-get install -y --no-install-recommends fonts-dejavu && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App-Code + Templates + Daten
COPY . .

# HF setzt PORT zur Laufzeit – nutze diese Variable
ENV PORT=7860
EXPOSE 7860

# Start: UVicorn erwartet "Datei:Variable" -> app.py enthält FastAPI-Instanz "app"
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
