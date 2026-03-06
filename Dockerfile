# ADR Tool API - Dockerfile
# Multi-stage build for production

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user for security
RUN groupadd -r adrtool && useradd -r -g adrtool adrtool

# Copy Python packages from builder
COPY --from=builder /root/.local /home/adrtool/.local
ENV PATH=/home/adrtool/.local/bin:$PATH

# Copy application code
COPY --chown=adrtool:adrtool . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Expose port
EXPOSE 8000

# Switch to non-root user
USER adrtool

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
