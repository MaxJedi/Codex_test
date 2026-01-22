from pydantic import BaseModel, Field


class TopicIdea(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=200)


class TopicsGenerateRequest(BaseModel):
    n: int = Field(default=8, ge=1, le=50)
    hint: str | None = Field(default=None, description="Опциональная подсказка/тематика для генерации")


class TopicsGenerateResponse(BaseModel):
    topics: list[TopicIdea]


class TopicsOverlayParams(BaseModel):
    # Layout
    title_y: float = Field(default=0.12, ge=0.0, le=1.0, description="Y верхней грани заголовка (0..1)")
    padding_pct: float = Field(default=5.0, ge=0.0, le=40.0)
    line_spacing: int = Field(default=4, ge=0, le=100)

    # Auto-fit
    coverage_min_pct: float = Field(default=8.0, ge=0.0, le=100.0)
    coverage_max_pct: float = Field(default=18.0, ge=0.0, le=100.0)
    words_min: int = Field(default=3, ge=1, le=50)
    words_max: int = Field(default=14, ge=1, le=50)
    min_font_size: int = Field(default=14, ge=1, le=300)
    base_font_size: int = Field(default=120, ge=10, le=400)

    # Styling
    align: str = Field(default="center")
    center_x: float = Field(default=0.5, ge=0.0, le=1.0)
    font_color: str = Field(default="#ffffff")
    outline_color: str = Field(default="#000000")
    outline_width: int = Field(default=2, ge=0, le=20)
    font_path: str | None = Field(default=None, description="Путь к шрифту (опционально)")


class TopicsOverlayRequest(BaseModel):
    path: str = Field(..., description="Абсолютный путь к видео (внутри FILE_BROWSER_ROOT)")
    topics: list[TopicIdea] = Field(..., min_length=1)
    params: TopicsOverlayParams = Field(default_factory=TopicsOverlayParams)


class TopicsOverlayItem(BaseModel):
    title: str
    description: str
    output_path: str
    download_url: str | None = None


class TopicsOverlayResponse(BaseModel):
    source_path: str
    results: list[TopicsOverlayItem]

