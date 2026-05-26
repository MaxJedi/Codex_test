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
    OPENAI_IMAGE_MODEL: str = Field(default='gpt-image-1', env='OPENAI_IMAGE_MODEL')
    CAROUSEL_IMAGE_BACKGROUND_SIZE: str = Field(default='1024x1536', env='CAROUSEL_IMAGE_BACKGROUND_SIZE')
    CAROUSEL_IMAGE_ILLUSTRATION_SIZE: str = Field(default='1024x1024', env='CAROUSEL_IMAGE_ILLUSTRATION_SIZE')
    CAROUSEL_IMAGE_GENERATION_ENABLED: bool = Field(default=True, env='CAROUSEL_IMAGE_GENERATION_ENABLED')
    RUNWAY_API_KEY: str
    
    DATA_DIR: str = Field(default='data', env='DATA_DIR')
    LOG_LEVEL: str = Field(default='INFO', env='LOG_LEVEL')
    LOG_FILE: str = Field(default='data/logs/app.log', env='LOG_FILE')
    CAROUSELS_DIRNAME: str = Field(default='carousels', env='CAROUSELS_DIRNAME')
    CAROUSEL_JOB_TTL_SECONDS: int = Field(default=7200, env='CAROUSEL_JOB_TTL_SECONDS')
    FILE_BROWSER_ROOT: str = Field(default='/', env='FILE_BROWSER_ROOT')
    FRAMES_DIR: str = Field(default='frames', env='FRAMES_DIR')
    VIDEO_SHOTS_DIRNAME: str = Field(default='video_shots', env='VIDEO_SHOTS_DIRNAME')
    IMAGES_DIRNAME: str = Field(default='images', env='IMAGES_DIRNAME')
    VIDEO_DEFAULT_RATIO: str = Field(default='1080:1920', env='VIDEO_DEFAULT_RATIO')
    REELS_DEFAULT_COUNT: int = Field(default=1, env='REELS_DEFAULT_COUNT')
    CAROUSEL_FONTS_DIR: str = Field(default='fonts', env='CAROUSEL_FONTS_DIR')
    DRAW_TEXT_FONT_PATH: str = Field(default='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', env='DRAW_TEXT_FONT_PATH')
    CAROUSEL_FONT_FALLBACK_PATHS: str = Field(
        default='/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf,'
                '/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf,'
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        env='CAROUSEL_FONT_FALLBACK_PATHS',
    )
    DEFAULT_SEARCH_VIDEOS_COUNT: int = Field(default=1, env='DEFAULT_SEARCH_VIDEOS_COUNT')
    class Config:
        env_file = '.env'
        extra = 'ignore'

try:
    settings = Settings()
except ValidationError as e:
    print('Missing configuration:', e, file=sys.stderr)
    raise SystemExit(1)

