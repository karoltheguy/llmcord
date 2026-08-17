FROM python:3.13-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# Globbed so a new module does not have to be added here to reach the image.
COPY *.py config.yaml ./

# UID 1000 matches the usual first host account, so the bind-mounted ./data
# stays writable. Override with `user:` in compose if your host UID differs.
RUN useradd --create-home --uid 1000 llmcord
USER llmcord

CMD ["python", "llmcord.py"]
