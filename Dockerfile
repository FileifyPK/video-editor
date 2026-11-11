FROM python:3.12-slim

# Avoid prompts from debian frontends
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIDEO_EDITOR_HOST=0.0.0.0 \
    VIDEO_EDITOR_PORT=5000

# Install FFmpeg and clean apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and create data directories
COPY . .
RUN mkdir -p uploads/videos uploads/logo uploads/intro uploads/outro uploads/mid uploads/audio uploads/images outputs temp && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["python", "app.py"]
