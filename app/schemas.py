from __future__ import annotations
from datetime import datetime, timedelta
from typing import List, Literal
from pydantic import BaseModel, Field


class Candidate(BaseModel):
    video_id: str
    title: str
    channel_title: str
    published_at: datetime
    view_count: int
    like_count: int
    is_shorts: bool


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


class VoiceLine(BaseModel):
    role: str
    text: str


class Scene(BaseModel):
    duration_sec: int = Field(ge=0)
    visual_description: str
    voice_lines: List[VoiceLine]


class ScenarioMeta(BaseModel):
    topic: str
    source: str


class Scenario(BaseModel):
    scenes: List[Scene]
    meta: ScenarioMeta


class StoryScene(Scene):
    broll_hints: List[str]
    tempo: str
    transitions: str


class Storyboard(BaseModel):
    scenes: List[StoryScene]
    total_duration_sec: int
    target: Literal["shorts", "youtube"]
