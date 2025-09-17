from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List

from app.schemas import Candidate
from app.services import search_trending
from app.core.settings import settings

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.post("/search", response_model=List[Candidate])
def search(payload: dict):
    try:
        topic = payload["topic"]
        n = int(payload.get("n", 5))
        region = payload.get("region", settings.REGION_CODE)
        published_after = payload.get("published_after", settings.DEFAULT_PUBLISHED_AFTER)
        shorts = bool(payload.get("shorts", True))
    except KeyError as e:
        raise HTTPException(400, f"Missing field {e}")
    
    # Validate and normalize RFC3339 timestamp (e.g., 2025-09-01T00:00:00Z)
    try:
        ts = published_after
        if isinstance(ts, str) and ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        # Normalize to Z-suffix
        published_after_norm = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        raise HTTPException(400, "published_after must be RFC3339, e.g. 2025-09-01T00:00:00Z")

    return search_trending(topic, n, region, published_after_norm, shorts)
