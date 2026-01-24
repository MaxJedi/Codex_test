from typing import Literal

from pydantic import BaseModel, Field


class TopicIdea(BaseModel):
    title: str
    description: str
    long_description: str | None = None


class TopicsGenerateRequest(BaseModel):
    n: int = Field(default=8, ge=1, le=50)
    hint: str | None = Field(default=None, description="Опциональная подсказка/тематика для генерации")


class TopicsGenerateResponse(BaseModel):
    topics: list[TopicIdea]


class TopicsOverlayParams(BaseModel):
    title_y: float = Field(default=0.12, ge=0.0, le=1.0, description="Y позиции заголовка (0..1)")
    padding_pct: float = Field(default=5.0, ge=0.0, le=40.0)
    coverage_min_pct: float = Field(default=8.0, ge=0.0, le=100.0)
    coverage_max_pct: float = Field(default=18.0, ge=0.0, le=100.0)
    words_min: int = Field(default=3, ge=1, le=50)
    words_max: int = Field(default=14, ge=1, le=50)
    min_font_size: int = Field(default=14, ge=6, le=200)
    base_font_size: int = Field(default=120, ge=20, le=400)
    align: Literal["left", "center", "right"] = Field(default="center")


class TopicsOverlayRequest(BaseModel):
    path: str = Field(..., description="Абсолютный путь к видео (внутри FILE_BROWSER_ROOT)")
    topics: list[TopicIdea] = Field(..., min_length=1)
    params: TopicsOverlayParams = Field(default_factory=TopicsOverlayParams)


class TopicsOverlayItem(BaseModel):
    title: str
    description: str
    long_description: str | None = None
    output_path: str
    download_url: str | None = None


class TopicsOverlayResponse(BaseModel):
    source_path: str
    results: list[TopicsOverlayItem]

