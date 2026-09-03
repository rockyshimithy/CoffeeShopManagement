FROM ghcr.io/astral-sh/uv:latest AS uv_bin
FROM python:3.12-slim

WORKDIR /app

# Copy uv binaries into the system path
COPY --from=uv_bin /uv /uvx /bin/

# Copy dependency definition file
COPY pyproject.toml ./

# Install dependencies globally into the container system Python using uv
RUN uv pip install --system -r pyproject.toml

# Copy application source code into the container
COPY . .

# Prevent Python from writing .pyc files to disc and enable unbuffered output for logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000