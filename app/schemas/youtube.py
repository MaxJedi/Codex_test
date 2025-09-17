from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class Candidate(BaseModel):
    video_id: str
    title: str
    channel_title: str
    published_at: datetime
    view_count: int
    like_count: int
    is_shorts: bool
