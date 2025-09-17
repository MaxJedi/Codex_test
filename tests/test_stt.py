from types import SimpleNamespace

import pytest

from app import stt


class _DummyClient:
    def __init__(self, response):
        self._response = response
        self.audio = SimpleNamespace(transcriptions=self)

    def create(self, *args, **kwargs):
        return self._response


def _patch_client(monkeypatch, response):
    monkeypatch.setattr(stt, "client", _DummyClient(response))


def _write_audio(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake-audio")
    return audio_path


def test_transcribe_with_segment_objects(monkeypatch, tmp_path):
    segments = [
        SimpleNamespace(text="hello", start=0.0, end=1.0),
        SimpleNamespace(text="world", start=1.0, end=2.0),
    ]
    response = SimpleNamespace(segments=segments)
    _patch_client(monkeypatch, response)

    transcript = stt.transcribe(str(_write_audio(tmp_path)))

    assert [s.text for s in transcript.segments] == ["hello", "world"]
    assert [s.start for s in transcript.segments] == [0.0, 1.0]
    assert [s.end for s in transcript.segments] == [1.0, 2.0]


def test_transcribe_with_dict_response(monkeypatch, tmp_path):
    payload = {
        "segments": [
            {"text": "line", "start": 0.0, "end": 3.5},
        ]
    }

    class Response:
        def dict(self):
            return payload

    _patch_client(monkeypatch, Response())

    transcript = stt.transcribe(str(_write_audio(tmp_path)))

    assert len(transcript.segments) == 1
    assert transcript.segments[0].text == "line"
    assert transcript.segments[0].start == 0.0
    assert transcript.segments[0].end == 3.5


def test_transcribe_without_segments(monkeypatch, tmp_path):
    class Response:
        def dict(self):
            return {}

    _patch_client(monkeypatch, Response())

    with pytest.raises(ValueError, match="did not include segments"):
        stt.transcribe(str(_write_audio(tmp_path)))
