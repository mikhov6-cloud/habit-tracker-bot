FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

# SQLite file lives here; mount a volume on /app/data in production if you want persistence
RUN mkdir -p /app/data

CMD ["python", "-m", "bot.main"]
