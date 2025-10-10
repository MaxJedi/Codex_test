from typing import Optional

from app.integrations.runway import RunwayIntegration, RunwayTaskResult


class RunwayVideoService:
    """Service layer for Runway text-to-video and image+text-to-video generation."""

    def __init__(self, runway: Optional[RunwayIntegration] = None) -> None:
        self._runway = runway or RunwayIntegration()

    def generate_from_text(
        self,
        prompt_text: str,
        *,
        model: str | None = "veo3",
        ratio: str = "1280:720",
        duration: int = 8,
    ) -> RunwayTaskResult:
        """Generate a video from text prompt using Runway.

        Returns a validated RunwayTaskResult with optional output_url.
        """
        return self._runway.text_to_video(
            prompt_text=prompt_text,
            model=model,
            ratio=ratio,
            duration=duration,
        )

    def generate_from_image_and_text(
        self,
        image_path: str,
        prompt_text: str,
        *,
        model: str | None = None,
        ratio: str = "1280:720",
        duration: int = 5,
        mime_type: str = "image/png",
    ) -> RunwayTaskResult:
        """Generate a video from an image and text prompt using Runway.

        image_path should point to a local image file. mime_type should match the image.
        """
        return self._runway.image_and_text_to_video(
            image_path=image_path,
            prompt_text=prompt_text,
            model=model,
            ratio=ratio,
            duration=duration,
            mime_type=mime_type,
        )


