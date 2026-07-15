FROM python:3.11-slim

WORKDIR /app

# System deps that some audio/voice libraries (Pipecat, etc.) may need at build/runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml ./
# If you have a lockfile (poetry.lock / uv.lock), copy it too so builds are reproducible:
# COPY poetry.lock ./
# COPY uv.lock ./

# Install the project itself + dependencies declared in pyproject.toml
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir .

# Now copy the rest of the application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
