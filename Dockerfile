FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Systemlibs für WeasyPrint (Cairo/Pango/GDK-Pixbuf/GLib) + Fonts
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

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV PORT=7860
EXPOSE 7860

# Wichtig: Hier auf dein ENTRYPOINT zeigen (main:app),
# NICHT "app:app", damit kein Konflikt mit dem app/ Ordner entsteht
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
