# Costco Price Check -- production image.
# Uses Docker specifically so we can apt-install the Tesseract OCR binary, which
# free non-Docker hosts don't allow.
FROM python:3.12-slim

# System deps: Tesseract OCR engine + English language data.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render (and most PaaS) inject the port to bind on via $PORT.
ENV PORT=8080
EXPOSE 8080

# gunicorn serves the Flask `app`. One worker with threads keeps memory low on
# the 512MB free instance (two workers running Tesseract can OOM), while threads
# still allow a couple of concurrent users.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120"]
