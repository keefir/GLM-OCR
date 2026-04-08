FROM python:3.12.9-slim

WORKDIR /app

# Install system dependencies
# libgl1 and libglib2.0-0 are often required by OpenCV and image processing libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies including the server extras
RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \ 
    uv sync \
            --locked \
            --no-dev \
            --no-install-project

# Expose default port
EXPOSE 5002

# Command to run the server
CMD ["uv", "run", "-m", "glmocr.server", "--config", "config.yaml", "--log-level", "DEBUG"]
