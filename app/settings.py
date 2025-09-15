import logging
import sys
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    YOUTUBE_API_KEY: str = Field(env='YOUTUBE_API_KEY')
    OPENAI_API_KEY: str = Field(env='OPENAI_API_KEY')
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(env='GOOGLE_APPLICATION_CREDENTIALS')
    REGION_CODE: str = Field(env='REGION_CODE')
    DEFAULT_PUBLISHED_AFTER: str = Field(env='DEFAULT_PUBLISHED_AFTER')
    LOG_LEVEL: str = Field(default='INFO', env='LOG_LEVEL')
    YOUTUBE_MAX_RETRIES: int = Field(default=3, ge=1, env='YOUTUBE_MAX_RETRIES')


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(level=level, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')


try:
    settings = Settings()
except ValidationError as e:
    print('Missing configuration:', e, file=sys.stderr)
    raise SystemExit(1)
else:
    _configure_logging(settings.LOG_LEVEL)
