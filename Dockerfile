FROM python:3.13-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.lock ./

# Wheels only, verified against the hashes in the lock. See CONTRIBUTING.md
# for how to regenerate the lock when requirements.txt changes.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock

# Globbed so a new module does not have to be added here to reach the image.
COPY *.py config.yaml ./

# The bot only writes to /app/data (the rest of /app is mounted read-only), so
# the image owns that directory and a fresh volume inherits the ownership.
RUN useradd --create-home --uid 1000 llmcord \
    && mkdir -p /app/data \
    && chown llmcord:llmcord /app/data
USER llmcord

CMD ["python", "llmcord.py"]
