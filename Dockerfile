# Multi-stage build for optimized image
FROM python:3.11-slim-bullseye as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim-bullseye

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libssl1.1 \
    libffi7 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 mpiservice && \
    mkdir -p /app && \
    chown -R mpiservice:mpiservice /app

WORKDIR /app

# Copy application code
COPY --chown=mpiservice:mpiservice ./src /app/src

# Switch to non-root user
USER mpiservice

# Environment variables for performance
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PYTHONIOENCODING=utf-8 \
    # Uvloop for performance
    UVLOOP_USE_LIBUV=1 \
    # Connection pools
    CONNECTION_POOL_SIZE=100 \
    REDIS_POOL_SIZE=50 \
    MONGO_POOL_SIZE=50

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run with optimized settings
CMD ["python", "-m", "uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--log-level", "info", \
     "--no-access-log"]