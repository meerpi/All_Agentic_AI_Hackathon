# Use official Python 3.12 thin image
FROM python:3.12-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition
COPY requirements.txt .

# Install Python packages & Playwright browser binaries for web automation
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium || true

# Copy source code, databases, credentials, and configurations
COPY . .

# Ensure data runtime directories exist
RUN mkdir -p data/checkpoints data/workflows data/audit_logs

# Expose port (Cloud Run sets and injects PORT env variable, default 8080)
ENV PORT=8080
EXPOSE 8080

# Run FastAPI app with Uvicorn worker bound to $PORT
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}

