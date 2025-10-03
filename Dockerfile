# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY src ./src
COPY .env.example ./.env.example

EXPOSE 8000

# Run our extended app (note --app-dir for src/)
CMD ["uvicorn", "--app-dir", "src", "hello_a2a_ica4aa.service:app", "--host", "0.0.0.0", "--port", "8000"]
