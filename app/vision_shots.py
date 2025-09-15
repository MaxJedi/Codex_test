from google.cloud import videointelligence
from .schemas import Shot


def detect_shots(file_path: str):
    client = videointelligence.VideoIntelligenceServiceClient()
    with open(file_path, "rb") as f:
        input_content = f.read()
    operation = client.annotate_video(
        request={"features": [videointelligence.Feature.SHOT_CHANGE_DETECTION], "input_content": input_content}
    )
    result = operation.result(timeout=180)
    annotation = result.annotation_results[0]
    shots = []
    for shot in annotation.shot_annotations:
        start = shot.start_time_offset.total_seconds()
        end = shot.end_time_offset.total_seconds()
        shots.append(Shot(start_sec=start, end_sec=end))
    return shots
