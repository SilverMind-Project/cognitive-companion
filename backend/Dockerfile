FROM python:3.12-slim AS base

# Install uv and ffmpeg
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --frozen --no-dev --extra gemini --no-install-project

# Copy application code
COPY backend/ backend/
COPY config/ config/

# Install the project itself (editable-ish, into the same venv)
RUN cd backend && uv sync --frozen --no-dev --extra gemini

# Create data directory
RUN mkdir -p data

EXPOSE 8000

CMD ["backend/.venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
