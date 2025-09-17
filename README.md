# Storyflow Pipeline

Pipeline для анализа YouTube Shorts и построения сценария/раскадровки.

## Требования

- Python 3.11
- Все зависимости указаны в `requirements.txt`

## Настройка

1. Создайте файл `.env` со значениями:
```
YOUTUBE_API_KEY=DEMO_KEY_DO_NOT_USE_IN_PROD
OPENAI_API_KEY=DEMO_OPENAI_KEY
GOOGLE_APPLICATION_CREDENTIALS=secrets/gcp_sa.json
REGION_CODE=RU
DEFAULT_PUBLISHED_AFTER=2025-08-01T00:00:00Z
COBALT_BASE_URL=http://localhost:9000
COBALT_VIDEO_QUALITY=720
OPENAI_TIMEOUT_SECONDS=350
OPENAI_MAX_RETRIES=2
```
2. Установите зависимости:
```
pip install -r requirements.txt
```

## Настройка Cobalt для скачивания видео

Проект использует [Cobalt](https://github.com/wukko/cobalt) для скачивания видео с YouTube.

### Вариант 1: Docker Compose (рекомендуется)

1. Скачайте docker-compose.yml для Cobalt:
```bash
curl -o cobalt-compose.yml https://raw.githubusercontent.com/wukko/cobalt/current/docker-compose.yml
```

2. Запустите Cobalt:
```bash
docker-compose -f cobalt-compose.yml up -d
```

Cobalt будет доступен на `http://localhost:9000`

### Вариант 2: Публичная инстанция

Используйте публичную инстанцию (может быть нестабильно):
```bash
# В .env файле:
COBALT_BASE_URL=https://co.wuk.sh
```

### Вариант 3: Локальная установка

1. Клонируйте репозиторий Cobalt:
```bash
git clone https://github.com/wukko/cobalt.git
cd cobalt
```

2. Установите зависимости:
```bash
npm install
```

3. Запустите сервер:
```bash
npm start
```

### Проверка подключения

Проверьте, что Cobalt работает:
```bash
curl http://localhost:9000/
```

Должен вернуться HTML страница Cobalt API.

### Настройка параметров Cobalt

В `.env` файле можно настроить:

- `COBALT_BASE_URL` - URL вашей инстанции Cobalt (по умолчанию: http://localhost:9000)
- `COBALT_VIDEO_QUALITY` - качество видео: 720, 1080, max (по умолчанию: 720)

### Устранение неполадок

**Ошибка "COBALT_BASE_URL is not set":**
- Убедитесь, что в `.env` файле задан `COBALT_BASE_URL`
- Перезапустите приложение после изменения `.env`

**Ошибка "Cobalt HTTP error 400/500":**
- Проверьте, что Cobalt сервер запущен: `curl http://localhost:9000/`
- Убедитесь, что видео доступно для скачивания
- Проверьте логи Cobalt: `docker-compose -f cobalt-compose.yml logs`

**Таймаут при скачивании:**
- Увеличьте `OPENAI_TIMEOUT_SECONDS` в `.env`
- Проверьте скорость интернет-соединения
- Попробуйте другую инстанцию Cobalt

## Структура проекта

```
app/
├── core/
│   ├── settings.py     # Конфигурация приложения
│   └── cli.py          # CLI интерфейс
├── schemas/
│   ├── youtube.py      # Модели для YouTube API
│   ├── media.py        # Модели медиа-данных (транскрипт, шоты)
│   └── content.py      # Модели контента (сценарий, раскадровка)
├── services/
│   ├── youtube_service.py    # Работа с YouTube API
│   ├── stt_service.py        # Транскрибация речи
│   ├── vision_service.py     # Анализ видео через OpenAI Vision
│   ├── scenario_service.py   # Генерация сценария
│   ├── storyboard_service.py # Создание раскадровки
│   └── storage_service.py    # Сохранение промежуточных данных
├── routers/
│   ├── youtube.py      # REST API для YouTube (/youtube/*)
│   ├── media.py        # REST API для медиа (/media/*)
│   └── content.py      # REST API для контента (/content/*)
├── integrations/
│   └── cobalt.py       # Интеграция с Cobalt для загрузки видео
└── main.py             # FastAPI приложение
```

## Запуск REST API
```
uvicorn app.main:app --reload
```

### Новые эндпоинты (рекомендуется):
- `POST /youtube/search` – поиск трендов YouTube
- `POST /media/analyze` – анализ видео (транскрипт + шоты)
- `POST /content/scenario` – генерация сценария
- `POST /content/storyboard` – создание раскадровки

### Legacy эндпоинты (устарели):
- `POST /search` – поиск трендов
- `POST /analyze` – транскрибация и шоты  
- `POST /scenario` – генерация сценария
- `POST /storyboard` – агентная раскадровка

## Запуск CLI
```
python -m app.core.cli search --topic "айфон лайфхаки" --n 5 --region RU --after "2025-08-01T00:00:00Z" --no-shorts
python -m app.core.cli analyze --video-id YyyZzz123
python -m app.core.cli scenario --video-id YyyZzz123 --topic "айфон лайфхаки"
python -m app.core.cli storyboard --scenario path/to/scenario.json --target shorts
```

Флаг `--shorts` включён по умолчанию и оставляет подборку роликов YouTube Shorts. Используйте `--no-shorts`, чтобы исключить Shorts из выдачи поиска.

## Сохранение промежуточных данных

Все результаты анализа сохраняются в `data/<video_id>/`:
- `transcript.json` – результат транскрибации
- `vision.json` – шоты и ключевые объекты  
- `scenario_messages.json` – готовый payload для OpenAI (генерация сценария)

## Тесты
```
CI=true pytest
```
