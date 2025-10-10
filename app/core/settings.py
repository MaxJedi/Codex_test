import sys
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    YOUTUBE_API_KEY: str = Field(..., env='YOUTUBE_API_KEY')
    OPENAI_API_KEY: str = Field(..., env='OPENAI_API_KEY')
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(..., env='GOOGLE_APPLICATION_CREDENTIALS')
    REGION_CODE: str = Field(..., env='REGION_CODE')
    DEFAULT_PUBLISHED_AFTER: str = Field(..., env='DEFAULT_PUBLISHED_AFTER')
    COBALT_BASE_URL: str | None = Field(default=None, env='COBALT_BASE_URL')
    COBALT_VIDEO_QUALITY: str = Field(default='720', env='COBALT_VIDEO_QUALITY')
    # OPENAI_HTTP_PROXY: str | None = Field(default=None, env='OPENAI_HTTP_PROXY')
    # OPENAI_HTTPS_PROXY: str | None = "https://sfYQ16:Uf3L4s@168.80.83.91:8000/"
    OPENAI_TIMEOUT_SECONDS: int = Field(default=700, env='OPENAI_TIMEOUT_SECONDS')
    OPENAI_MAX_RETRIES: int = Field(default=2, env='OPENAI_MAX_RETRIES')
    RUNWAY_API_KEY: str

    class Config:
        env_file = '.env'
        extra = 'ignore'

try:
    settings = Settings()
except ValidationError as e:
    print('Missing configuration:', e, file=sys.stderr)
    raise SystemExit(1)

