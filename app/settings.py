import sys
from pydantic import BaseSettings, Field, ValidationError
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    YOUTUBE_API_KEY: str = Field(..., env='YOUTUBE_API_KEY')
    OPENAI_API_KEY: str = Field(..., env='OPENAI_API_KEY')
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(..., env='GOOGLE_APPLICATION_CREDENTIALS')
    REGION_CODE: str = Field(..., env='REGION_CODE')
    DEFAULT_PUBLISHED_AFTER: str = Field(..., env='DEFAULT_PUBLISHED_AFTER')

    class Config:
        env_file = '.env'
        extra = 'ignore'

try:
    settings = Settings()
except ValidationError as e:
    print('Missing configuration:', e, file=sys.stderr)
    raise SystemExit(1)
