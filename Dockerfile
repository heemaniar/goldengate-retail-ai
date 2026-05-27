# ── MallPulse — Cloud Run container ──────────────────────────────────────────
# Runs the Streamlit chat UI on port 8080.
# Auth to GCP (BigQuery, Vertex AI) is provided automatically by the
# Cloud Run service account via Application Default Credentials — no key file
# needed inside the image.

FROM python:3.12-slim

# System libraries needed by some packages at compile time
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache: only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# ── Runtime configuration ─────────────────────────────────────────────────────
# Cloud Run injects PORT (usually 8080). Streamlit reads these env vars.
ENV PORT=8080
ENV STREAMLIT_SERVER_PORT=8080
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

EXPOSE 8080

CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
