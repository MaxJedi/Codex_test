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
        build-essential \
        yasm \
        nasm \
        cmake \
        pkg-config \
        libx264-dev \
        libx265-dev \
        libvpx-dev \
        libmp3lame-dev \
        libopus-dev \
        libvorbis-dev \
        libtheora-dev \
        libfreetype6-dev \
        libfontconfig1-dev \
        git \
    && cd /tmp \
    && git clone --depth 1 --branch n6.1.1 https://git.ffmpeg.org/ffmpeg.git ffmpeg-src \
    && cd ffmpeg-src \
    && ./configure \
        --prefix=/usr/local \
        --enable-gpl \
        --enable-libx264 \
        --enable-libx265 \
        --enable-libvpx \
        --enable-libmp3lame \
        --enable-libopus \
        --enable-libvorbis \
        --enable-libtheora \
        --enable-libfreetype \
        --enable-libfontconfig \
        --enable-nonfree \
        --disable-debug \
        --disable-doc \
        --disable-ffplay \
        --extra-cflags="-O3" \
        --extra-ldflags="-Wl,-rpath,/usr/local/lib" \
    && make -j$(nproc) \
    && make install \
    && ldconfig \
    && cd / \
    && rm -rf /tmp/ffmpeg-src \
    && apt-get purge -y build-essential yasm nasm cmake pkg-config git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version | head -1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


