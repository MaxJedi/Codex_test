import pytest
from app.schemas import (
    Candidate,
    VoiceLine,
    Storyboard,
    StoryScene,
    KeyObject,
    AnalysisResult,
    Transcript,
    Segment,
    Shot,
)


def test_candidate_invalid():
    with pytest.raises(Exception):
        Candidate()


def test_analysis_result_schema():
    transcript = Transcript(segments=[Segment(text="hi", start=0, end=1)])
    shots = [Shot(start_sec=0, end_sec=1)]
    key_objects = [KeyObject(description="phone", category="tech", confidence=0.9, start_sec=0, end_sec=1)]
    result = AnalysisResult(transcript=transcript, shots=shots, key_objects=key_objects)
    assert result.key_objects[0].description == "phone"


def test_storyboard_model():
    Storyboard(
        scenes=[
            StoryScene(
                duration_sec=50,
                visual_description="v",
                voice_lines=[VoiceLine(role="n", text="hi")],
                broll_hints=["clip"],
                tempo="fast",
                transitions="cut",
            )
        ],
        total_duration_sec=50,
        target="shorts",
    )


def test_storyboard_invalid_duration():
    with pytest.raises(Exception):
        Storyboard(
            scenes=[
                StoryScene(
                    duration_sec=20,
                    visual_description="v",
                    voice_lines=[VoiceLine(role="n", text="hi")],
                    broll_hints=[],
                    tempo="fast",
                    transitions="cut",
                )
            ],
            total_duration_sec=20,
            target="shorts",
        )
