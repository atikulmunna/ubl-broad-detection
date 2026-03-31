# AI Worker - Production Dockerfile

FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV USE_LOCALSTACK=false

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --timeout 1000 --retries 5 -r requirements.txt

# Copy application code and utilities
COPY main.py .
COPY utils/ ./utils/
COPY core/ ./core/

# Copy config directory (standards files)
COPY config/ ./config/

# Models directory will be mounted from host
# Expected at /app/models/ via volume mount

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "print('healthy')" || exit 1

CMD ["python3", "main.py"]
