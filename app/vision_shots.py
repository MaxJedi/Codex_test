import logging
from google.cloud import videointelligence
from .schemas import Shot, KeyObject, VisionInsights

logger = logging.getLogger(__name__)


def _offset_to_seconds(offset) -> float:
    if hasattr(offset, "total_seconds"):
        return float(offset.total_seconds())
    return float(offset or 0)


def detect_shots(file_path: str) -> VisionInsights:
    logger.debug("Starting shot and label detection for %s", file_path)
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
            "video_context": {
                "label_detection_config": {
                    "label_detection_mode": videointelligence.LabelDetectionMode.SHOT_MODE,
                    "stationary_camera": False,
                }
            },
        }
    )
    result = operation.result(timeout=180)
    annotation = result.annotation_results[0]
    shots = []
    for shot in getattr(annotation, "shot_annotations", []):
        start = _offset_to_seconds(shot.start_time_offset)
        end = _offset_to_seconds(shot.end_time_offset)
        shots.append(Shot(start_sec=start, end_sec=end))
    key_objects: list[KeyObject] = []
    for label in getattr(annotation, "segment_label_annotations", []):
        description = label.entity.description or ""
        category = label.category_entities[0].description if label.category_entities else None
        for segment in getattr(label, "segments", []):
            segment_range = getattr(segment, "segment", None)
            if segment_range is None:
                continue
            start = _offset_to_seconds(segment_range.start_time_offset)
            end = _offset_to_seconds(segment_range.end_time_offset)
            confidence = float(segment.confidence or 0)
            end_value = end if end >= start else start
            key_objects.append(
                KeyObject(
                    description=description,
                    category=category,
                    confidence=min(confidence, 1.0),
                    start_sec=start,
                    end_sec=end_value,
                )
            )
    logger.debug("Detected %s shots and %s key objects", len(shots), len(key_objects))
    return VisionInsights(shots=shots, key_objects=key_objects)
