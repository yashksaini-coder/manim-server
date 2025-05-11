FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the application into the container.
COPY . /app

# The installer requires curl (and certificates) to download the release archive
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# Install system dependencies for Manim
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    texlive \
    texlive-fonts-extra \
    texlive-latex-recommended \
    texlive-science \
    tipa \
    libffi-dev \
    git \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

    # Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it

RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin:$PATH"

# Install the application dependencies.
RUN uv sync --frozen --no-cache

# Run the application.
CMD ["uv", "run", "app.py"]