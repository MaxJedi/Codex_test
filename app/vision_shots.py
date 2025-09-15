from google.cloud import videointelligence
from .schemas import Shot, KeyObject


def _duration_to_seconds(duration) -> float:
    if not duration:
        return 0.0
    if hasattr(duration, "total_seconds"):
        return float(duration.total_seconds())
    seconds = float(getattr(duration, "seconds", 0.0))
    nanos = float(getattr(duration, "nanos", 0.0))
    return seconds + nanos / 1_000_000_000.0


def detect_shots(file_path: str):
    client = videointelligence.VideoIntelligenceServiceClient()
    with open(file_path, "rb") as f:
        input_content = f.read()
    operation = client.annotate_video(
        request={
            "features": [
                videointelligence.Feature.SHOT_CHANGE_DETECTION,
                videointelligence.Feature.LABEL_DETECTION,
            ],
            "input_content": input_content,
        }
    )
    result = operation.result(timeout=180)
    annotation_results = getattr(result, "annotation_results", [])
    if not annotation_results:
        return [], []
    annotation = annotation_results[0]
    shots = []
    for shot in getattr(annotation, "shot_annotations", []):
        start = _duration_to_seconds(getattr(shot, "start_time_offset", None))
        end = _duration_to_seconds(getattr(shot, "end_time_offset", None))
        shots.append(Shot(start_sec=start, end_sec=end))
    key_objects: list[KeyObject] = []

    def _collect_categories(entities) -> list[str]:
        return [
            entity.description
            for entity in entities or []
            if getattr(entity, "description", None)
        ]

    def _append_key_object(description: str, categories, segment, confidence):
        start = _duration_to_seconds(getattr(segment, "start_time_offset", None)) if segment else 0.0
        end = _duration_to_seconds(getattr(segment, "end_time_offset", None)) if segment else 0.0
        key_objects.append(
            KeyObject(
                description=description or "",
                categories=list(categories or []),
                start_sec=start,
                end_sec=end,
                confidence=confidence,
            )
        )

    for label in getattr(annotation, "shot_label_annotations", []):
        description = getattr(getattr(label, "entity", None), "description", "")
        categories = _collect_categories(getattr(label, "category_entities", []))
        for segment_info in getattr(label, "segments", []):
            segment = getattr(segment_info, "segment", None)
            confidence = getattr(segment_info, "confidence", None)
            _append_key_object(description, categories, segment, confidence)

    for label in getattr(annotation, "segment_label_annotations", []):
        description = getattr(getattr(label, "entity", None), "description", "")
        categories = _collect_categories(getattr(label, "category_entities", []))
        for segment_info in getattr(label, "segments", []):
            segment = getattr(segment_info, "segment", None)
            confidence = getattr(segment_info, "confidence", None)
            _append_key_object(description, categories, segment, confidence)

    for obj in getattr(annotation, "object_annotations", []):
        description = getattr(getattr(obj, "entity", None), "description", "")
        categories = _collect_categories(getattr(obj, "category_entities", []))
        segment = getattr(obj, "segment", None)
        confidence = getattr(obj, "confidence", None)
        _append_key_object(description, categories, segment, confidence)

    return shots, key_objects
