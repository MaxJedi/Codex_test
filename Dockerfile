FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (ffmpeg 6.1.1, curl for health/debug)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        wget \
        xz-utils \
    && cd /tmp \
    && wget https://github.com/BtbN/FFmpeg-Builds/releases/download/6.1.1/ffmpeg-6.1.1-linux64-gpl.tar.xz \
    && tar -xf ffmpeg-6.1.1-linux64-gpl.tar.xz \
    && mv ffmpeg-6.1.1-linux64-gpl/bin/ffmpeg /usr/local/bin/ \
    && mv ffmpeg-6.1.1-linux64-gpl/bin/ffprobe /usr/local/bin/ \
    && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe \
    && rm -rf /tmp/ffmpeg-6.1.1-linux64-gpl* \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


