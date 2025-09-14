import pytest
from app.schemas import Candidate, Scenario, ScenarioMeta, Scene, VoiceLine, Storyboard, StoryScene


def test_candidate_invalid():
    with pytest.raises(Exception):
        Candidate()


def test_storyboard_model():
    scenario = Scenario(
        scenes=[Scene(duration_sec=1, visual_description="v", voice_lines=[VoiceLine(role="n", text="hi")])],
        meta=ScenarioMeta(topic="t", source="s"),
    )
    board = Storyboard(
        scenes=[
            StoryScene(
                duration_sec=1,
                visual_description="v",
                voice_lines=[VoiceLine(role="n", text="hi")],
                broll_hints=[],
                tempo="fast",
                transitions="cut",
            )
        ],
        total_duration_sec=1,
        target="shorts",
    )
    assert board.target == "shorts"
