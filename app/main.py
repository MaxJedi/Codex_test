from fastapi import FastAPI

from app.routers import youtube_router, media_router, content_router
from app.core.secrets import ensure_secrets_dir

# Ensure secrets directory exists
ensure_secrets_dir()

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


# Include routers
app.include_router(youtube_router)
app.include_router(media_router)  
app.include_router(content_router)