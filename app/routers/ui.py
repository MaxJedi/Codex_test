from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


# @router.get("/overlay")
# def overlay_page(request: Request):
#     """Serve overlay build interface."""
#     return templates.TemplateResponse("overlay.html", {"request": request})


@router.get("/topics")
def topics_page(request: Request):
    """Serve topics generator UI."""
    return templates.TemplateResponse("topics.html", {"request": request})

