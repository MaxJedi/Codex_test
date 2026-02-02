from fastapi import FastAPI

from app.routers import ui_router, content_router
from app.core.secrets import ensure_secrets_dir

# Ensure secrets directory exists
ensure_secrets_dir()

app = FastAPI(
    title="Fabric API",
    description="API for Fabric",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
   
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Include routers
app.include_router(ui_router)
app.include_router(content_router)