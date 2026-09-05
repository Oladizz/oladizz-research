FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install system dependencies for WeasyPrint (fonts, cairo, pango) and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libpango1.0-dev \
    libcairo2 \
    libcairo2-dev \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY v2/requirements-dev.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    gunicorn \
    flask \
    trafilatura \
    beautifulsoup4 \
    markdown \
    weasyprint \
    google-cloud-firestore \
    google-cloud-storage

# Download spaCy English model
RUN python -m spacy download en_core_web_sm

# Copy application source code
COPY . /app

EXPOSE 8080

CMD exec gunicorn api_server:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 300
