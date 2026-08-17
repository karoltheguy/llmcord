FROM python:3.13-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.lock ./

# Wheels only, verified against the hashes in the lock. See CONTRIBUTING.md
# for how to regenerate the lock when requirements.txt changes.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock

# Globbed so a new module does not have to be added here to reach the image.
COPY *.py config.yaml ./

# UID 1000 matches the usual first host account, so the bind-mounted ./data
# stays writable. Override with `user:` in compose if your host UID differs.
RUN useradd --create-home --uid 1000 llmcord
USER llmcord

CMD ["python", "llmcord.py"]
