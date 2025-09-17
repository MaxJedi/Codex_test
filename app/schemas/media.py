from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


class Segment(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class Transcript(BaseModel):
    segments: List[Segment]


class Shot(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)


class KeyObject(BaseModel):
    description: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    categories: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    transcript: Transcript
    shots: List[Shot]
    key_objects: List[KeyObject] = Field(default_factory=list)
