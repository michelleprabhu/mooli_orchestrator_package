# MoolAI Orchestrator Service Docker Image
# Multi-stage build: Frontend + Backend
FROM node:18-alpine AS frontend-builder

# Build frontend
WORKDIR /app/frontend
COPY orchestrator/app/gui/frontend/package*.json ./
RUN npm install

COPY orchestrator/app/gui/frontend/ ./
RUN npm run build

# Backend stage
FROM python:3.10-slim

LABEL maintainer="MoolAI Team"
LABEL version="1.0"
LABEL description="MoolAI Orchestrator Service - AI workflow execution engine with integrated frontend"

# Set working directory
WORKDIR /app

# Set environment variables for better logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install DynaRoute with multiple fallback methods
RUN echo "🔍 Installing DynaRoute package..." && \
    (pip install dynaroute-client --no-cache-dir && echo "✅ dynaroute-client installed") || \
    (pip install dynaroute --no-cache-dir && echo "✅ dynaroute installed") || \
    (echo "⚠️ DynaRoute installation failed - will use OpenAI fallback")

# Verify DynaRoute installation
RUN python -c "import dynaroute; print('✅ DynaRoute successfully imported')" || \
    echo "⚠️ DynaRoute not available - application will use OpenAI fallback mode"

# Copy built frontend from frontend-builder stage
COPY --from=frontend-builder /app/frontend/dist ./app/gui/frontend/dist

# Download spaCy model for NLP processing
RUN python -m spacy download en_core_web_sm || true

# Copy application code
COPY orchestrator/app/ ./app/
COPY common/ ./common/

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Create non-root user for security
RUN useradd -m -u 1000 moolai && \
    chown -R moolai:moolai /app

USER moolai

# Expose orchestrator port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the orchestrator service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]