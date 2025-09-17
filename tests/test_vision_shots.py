from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from google.cloud import videointelligence

from app.vision_shots import detect_shots


class DurationStub:
    def __init__(self, seconds: float = 0.0, nanos: float = 0.0):
        self.seconds = seconds
        self.nanos = nanos

    def total_seconds(self) -> float:
        return float(self.seconds) + float(self.nanos) / 1_000_000_000.0


def _make_operation(result):
    operation = MagicMock()
    operation.result.return_value = result
    return operation


@patch("app.vision_shots.videointelligence.VideoIntelligenceServiceClient")
def test_detect_shots_parses_key_objects(mock_client_cls, tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    shot_annotation = SimpleNamespace(
        start_time_offset=DurationStub(0),
        end_time_offset=DurationStub(5),
    )
    label_segment = SimpleNamespace(
        segment=SimpleNamespace(
            start_time_offset=DurationStub(1),
            end_time_offset=DurationStub(4, 500_000_000),
        ),
        confidence=0.95,
    )
    label_annotation = SimpleNamespace(
        entity=SimpleNamespace(description="Car"),
        category_entities=[SimpleNamespace(description="Vehicle")],
        segments=[label_segment],
    )
    annotation_result = SimpleNamespace(
        shot_annotations=[shot_annotation],
        shot_label_annotations=[label_annotation],
        segment_label_annotations=[],
        object_annotations=[],
    )
    mock_result = SimpleNamespace(annotation_results=[annotation_result])

    mock_client = MagicMock()
    mock_client.annotate_video.return_value = _make_operation(mock_result)
    mock_client_cls.return_value = mock_client

    shots, key_objects = detect_shots(str(video_path))

    assert len(shots) == 1
    assert shots[0].start_sec == pytest.approx(0.0)
    assert shots[0].end_sec == pytest.approx(5.0)
    assert len(key_objects) == 1
    assert key_objects[0].description == "Car"
    assert key_objects[0].categories == ["Vehicle"]
    assert key_objects[0].confidence == pytest.approx(0.95)
    assert key_objects[0].start_sec == pytest.approx(1.0)
    assert key_objects[0].end_sec == pytest.approx(4.5)

    features = mock_client.annotate_video.call_args.kwargs["request"]["features"]
    assert videointelligence.Feature.LABEL_DETECTION in features
    assert videointelligence.Feature.SHOT_CHANGE_DETECTION in features


@patch("app.vision_shots.videointelligence.VideoIntelligenceServiceClient")
def test_detect_shots_handles_empty_annotations(mock_client_cls, tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    mock_client = MagicMock()
    mock_client.annotate_video.return_value = _make_operation(SimpleNamespace(annotation_results=[]))
    mock_client_cls.return_value = mock_client

    shots, key_objects = detect_shots(str(video_path))

    assert shots == []
    assert key_objects == []
