# One image for the API and the Celery worker (they differ only in the start
# command). Targets Render / Railway, or anything that runs a container.
#
# NOT built or run on the machine this project was developed on (no Docker
# there) -- see DEPLOYMENT.md for what was and wasn't verified.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Prophet drives a compiled Stan model. The Linux wheel ships it prebuilt, but
# a compiler is the fallback if pip has to build from source on this platform
# (Ch2 section 2.2.1: Windows dev machines need an extra toolchain step; the
# Linux deployment target only needs build-essential).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Generated report PDFs are written here; mount a persistent disk on this path
# if reports must survive a redeploy.
RUN mkdir -p /app/generated_reports

EXPOSE 8000

# Migrate, then serve. $PORT is set by the platform; 8000 locally.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
