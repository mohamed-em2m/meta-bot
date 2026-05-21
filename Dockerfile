FROM python:3.12-slim AS builder
# Switch to non-root user if desired (optional)
# RUN adduser --disabled-password appuser
# USER appuser

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y curl

RUN pip install uv

# Install build-time OS deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Use `uv pip` to install locked dependencies system-wide
RUN uv pip install --system --no-cache-dir -r pyproject.toml && uv pip check

# === STAGE 2: CLEAN & SLIM DEPENDENCIES ===
FROM python:3.12-slim AS cleaner
WORKDIR /usr/src/app

# Copy installed libraries and binaries from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

# Remove Python caches
RUN find /usr/local/lib/python3.12 -name "*.pyc" -delete \
    && find /usr/local/lib/python3.12 -name "__pycache__" -delete


# === STAGE 3: RUNTIME ===
FROM python:3.12-slim AS runtime
WORKDIR /usr/src/app

# Install only runtime OS dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       libsndfile1 \
       python3-pygame \
    && rm -rf /var/lib/apt/lists/*

# Copy cleaned Python environment
COPY --from=cleaner /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=cleaner /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Expose and run
EXPOSE 8080
CMD ["hypercorn", "meta_app_chatbot.main:app", "--bind", "0.0.0.0:8080", "--worker-class", "asyncio", "--log-level", "info", "--access-logfile", "-"]
