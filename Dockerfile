FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    texlive \
    texlive-fonts-extra \
    texlive-latex-recommended \
    texlive-science \
    tipa \
    git \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]