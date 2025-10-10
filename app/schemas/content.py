from __future__ import annotations
from typing import List, Literal
from pydantic import BaseModel, Field


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


class GeneratedVideo(BaseModel):
    task_id: str
    status: str
    url: str | None = None
