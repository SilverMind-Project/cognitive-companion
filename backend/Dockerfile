FROM python:3.12-slim AS base

# Install ffmpeg for video processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/pyproject.toml backend/pyproject.toml
RUN pip install --no-cache-dir "backend/.[gemini]"

# Copy application code
COPY backend/ backend/
COPY config/ config/

# Create data directory
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
