# Trusted evaluator environment. No firmware is copied into this build context.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends g++ git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.2.6
ENV PYTHONDONTWRITEBYTECODE=1
