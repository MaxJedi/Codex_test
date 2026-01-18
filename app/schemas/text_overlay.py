from typing import Literal

from pydantic import BaseModel, Field


class TextOverlayConfig(BaseModel):
    text: str = Field(..., description="Текст для наложения на видео")
    font_path: str | None = Field(default=None, description="Путь к TTF/OTF шрифту внутри контейнера")
    font_size: int = Field(default=48, ge=1, le=300, description="Размер шрифта")
    max_words_per_line: int = Field(default=7, ge=1, le=50, description="Максимум слов в строке перед переносом")
    align: Literal["left", "center", "right"] = Field(default="center", description="Выравнивание текста")
    center_x: float = Field(default=0.5, ge=0.0, le=1.0, description="Относительная X-координата центра текста (0..1)")
    center_y: float = Field(default=0.8, ge=0.0, le=1.0, description="Относительная Y-координата центра текста (0..1)")
    font_color: str = Field(default="white", description="Цвет шрифта (ffmpeg drawtext, напр. white, #ffffff)")
    outline_color: str = Field(default="black", description="Цвет обводки")
    outline_width: int = Field(default=2, ge=0, le=20, description="Толщина обводки")
    line_spacing: int = Field(default=4, ge=0, le=100, description="Межстрочный интервал")
    auto_fit: bool = Field(default=False, description="Автоподбор размера текста под ширину кадра (без ручного fontsize)")
    padding_pct: float = Field(default=5.0, ge=0.0, le=40.0, description="Отступы от краев кадра в процентах (для auto_fit)")
    auto_fit_base_font_size: int = Field(default=100, ge=10, le=400, description="Базовый fontsize для отрисовки перед масштабированием (auto_fit)")




