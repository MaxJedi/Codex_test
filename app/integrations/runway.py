import base64
from typing import Any

from pydantic import BaseModel
from runwayml import RunwayML, TaskFailedError

from app.core.settings import settings


class RunwayTaskResult(BaseModel):
    task_id: str
    status: str
    output_url: str | None = None
    raw: dict[str, Any]


class RunwayIntegration:
    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or settings.__dict__.get("RUNWAY_API_KEY")
        if not api_key:
            raise RuntimeError("RUNWAY_API_KEY is not set")
        self._client = RunwayML(api_key=api_key)

    def _extract_output_url(self, task_obj: Any) -> str | None:
        # SDK typically returns task.output as a list of URLs or dicts
        output = getattr(task_obj, "output", None)
        if isinstance(output, list) and output:
            first = output[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url") or first.get("video") or first.get("href")
        # Fallbacks
        url = getattr(task_obj, "result", None)
        if isinstance(url, str):
            return url
        return None

    def text_to_video(
        self,
        prompt_text: str,
        *,
        model: str | None = None,
        ratio: str = "1280:720",
        duration: int = 5,
    ) -> RunwayTaskResult:
        model = model or settings.__dict__.get("RUNWAY_MODEL_TEXT_TO_VIDEO", "gen4_turbo")
        # Ensure prompt is a plain string (SDK requires string, not object)
        if not isinstance(prompt_text, str):
            try:
                import json as _json
                prompt_text = _json.dumps(prompt_text, ensure_ascii=False)
            except Exception:
                prompt_text = str(prompt_text)
        try:
            task = (
                self._client.text_to_video.create(
                    model=model,
                    prompt_text=prompt_text,
                    ratio=ratio,
                    duration=duration,
                ).wait_for_task_output()
            )
        except TaskFailedError as e:
            raise RuntimeError(f"Runway task failed: {e}")

        return RunwayTaskResult(
            task_id=str(getattr(task, "id", "")),
            status=str(getattr(task, "status", "unknown")),
            output_url=self._extract_output_url(task),
            raw=getattr(task, "__dict__", {}) or {}
        )

    def image_and_text_to_video(
        self,
        image_path: str,
        prompt_text: str,
        *,
        model: str | None = None,
        ratio: str = "1280:720",
        duration: int = 5,
        mime_type: str = "image/png",
    ) -> RunwayTaskResult:
        model = model or settings.__dict__.get("RUNWAY_MODEL_IMAGE_TO_VIDEO", "gen4_turbo")
        # Ensure prompt is a plain string
        if not isinstance(prompt_text, str):
            try:
                import json as _json
                prompt_text = _json.dumps(prompt_text, ensure_ascii=False)
            except Exception:
                prompt_text = str(prompt_text)
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{base64_image}"

        try:
            task = (
                self._client.image_to_video.create(
                    model=model,
                    prompt_image=data_uri,
                    prompt_text=prompt_text,
                    ratio=ratio,
                    duration=duration,
                ).wait_for_task_output()
            )
        except TaskFailedError as e:
            raise RuntimeError(f"Runway task failed: {e}")

        return RunwayTaskResult(
            task_id=str(getattr(task, "id", "")),
            status=str(getattr(task, "status", "unknown")),
            output_url=self._extract_output_url(task),
            raw=getattr(task, "__dict__", {}) or {}
        )


