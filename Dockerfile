FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Systemdeps für WeasyPrint (Cairo/Pango/Fonts etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libharfbuzz0b \
    libfreetype6 \
    libfontconfig1 \
    libfribidi0 \
    libjpeg62-turbo \
    libpng16-16 \
    liblcms2-2 \
    libopenjp2-7 \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Erst Requirements kopieren (besseres Caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Dann den restlichen Code
COPY . .

# Laufzeit-Verzeichnisse (schreibbar für jeden, verhindert Permission-Probleme auf HF)
RUN mkdir -p /app/outputs /app/chroma_db && \
    chmod -R 777 /app/outputs /app/chroma_db

ENV PORT=7860
EXPOSE 7860

# Start FastAPI: "main:app" => Datei main.py, Variable app
CMD ["uvicorn", "main:main", "--host", "0.0.0.0", "--port", "7860"]
