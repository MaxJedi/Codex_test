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
GOOGLE_APPLICATION_CREDENTIALS=/app/creds/gcp_sa.json
REGION_CODE=RU
DEFAULT_PUBLISHED_AFTER=2025-08-01T00:00:00Z
```
2. Установите зависимости:
```
pip install -r requirements.txt
```

## Запуск REST API
```
uvicorn app.main:app --reload
```
Эндпоинты:
- `POST /search` – поиск трендов (Shorts или общие ролики)
- `POST /analyze` – транскрибация, шоты и ключевые объекты
- `POST /scenario` – генерация локализованного сценария (валидируется Pydantic)
- `POST /storyboard` – агентная раскадровка с контролем длительности

## Запуск CLI
```
python -m app.cli search --topic "айфон лайфхаки" --n 5 --region RU --after "2025-08-01T00:00:00Z"
python -m app.cli search --topic "айфон лайфхаки" --region RU --after "2025-08-01T00:00:00Z" --no-shorts
python -m app.cli analyze --video-id YyyZzz123
python -m app.cli scenario --video-id YyyZzz123 --topic "айфон лайфхаки"
python -m app.cli storyboard --scenario path/to/scenario.json --target shorts
```

## Тесты
```
CI=true pytest
```

## Схемы

- `Scenario`: `app/schemas.py::SCENARIO_JSON_SCHEMA`
- `Storyboard`: `app/schemas.py::STORYBOARD_JSON_SCHEMA`
