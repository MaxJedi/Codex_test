from __future__ import annotations
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.end < self.start:
            raise ValueError("Segment end must be greater or equal to start")
        return self


class Transcript(BaseModel):
    segments: List[Segment]


class Shot(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.end_sec < self.start_sec:
            raise ValueError("Shot end must be greater or equal to start")
        return self


class KeyObject(BaseModel):
    description: str
    category: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.end_sec < self.start_sec:
            raise ValueError("Key object end must be greater or equal to start")
        return self


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

    @model_validator(mode="after")
    def _validate_total_duration(self):
        total = sum(scene.duration_sec for scene in self.scenes)
        if total != self.total_duration_sec:
            raise ValueError("total_duration_sec must equal the sum of scene durations")
        if self.target == "shorts" and not (45 <= self.total_duration_sec <= 60):
            raise ValueError("Shorts storyboard must be between 45 and 60 seconds")
        if self.target == "youtube" and not (60 <= self.total_duration_sec <= 120):
            raise ValueError("YouTube storyboard must be between 60 and 120 seconds")
        return self


class VisionInsights(BaseModel):
    shots: List[Shot]
    key_objects: List[KeyObject]


class AnalysisResult(BaseModel):
    transcript: Transcript
    shots: List[Shot]
    key_objects: List[KeyObject]


SCENARIO_JSON_SCHEMA = Scenario.model_json_schema()
STORYBOARD_JSON_SCHEMA = Storyboard.model_json_schema()
