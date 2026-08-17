FROM python:3.13-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# Globbed so a new module does not have to be added here to reach the image.
COPY *.py config.yaml ./

CMD ["python", "llmcord.py"]
