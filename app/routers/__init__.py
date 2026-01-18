from app.routers.youtube import router as youtube_router
from app.routers.media import router as media_router
from app.routers.content import router as content_router
from app.routers.ui import router as ui_router

__all__ = ["youtube_router", "media_router", "content_router", "ui_router"]
