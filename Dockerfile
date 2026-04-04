FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
