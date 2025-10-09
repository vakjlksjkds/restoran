# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Системные пакеты (tzdata для часовых поясов)
RUN apt-get update && apt-get install -y --no-install-recommends \
	tzdata \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Папка для SQLite
ENV DB_PATH=/app/restaurant_bot.db
ENV PYTHONUNBUFFERED=1

CMD ["python", "simple_bot.py"]
