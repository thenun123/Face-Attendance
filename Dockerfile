# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for dlib / OpenCV / imgaug
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only torch first (saves ~1.5 GB vs default CUDA build)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.2.2+cpu \
        torchvision==0.17.2+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Only runtime libs — no build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# ── FIX: Point ALL model caches to /app/.cache (writable by appuser) ──────────
ENV TORCH_HOME=/app/.cache/torch
ENV XDG_CACHE_HOME=/app/.cache

# ── FIX: Pre-download FaceNet weights into /app/.cache while still root ────────
RUN mkdir -p /app/.cache && \
    python -c "from facenet_pytorch import InceptionResnetV1; InceptionResnetV1(pretrained='vggface2')" \
    || echo "Weight pre-download skipped (network unavailable at build time)"

# Local fallback dir for unknown face snapshots
RUN mkdir -p unknown_faces

# ── FIX: Give appuser ownership of ALL of /app including .cache ────────────────
RUN adduser --disabled-password --no-create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]