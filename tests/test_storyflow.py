import json
from app.schemas import Scenario, ScenarioMeta, Scene, VoiceLine
from app import llm_storyboard


def test_storyboard_generation(monkeypatch):
    scenario = Scenario(
        scenes=[Scene(duration_sec=10, visual_description="v", voice_lines=[VoiceLine(role="n", text="hi")])],
        meta=ScenarioMeta(topic="t", source="s"),
    )

    def fake_create(*args, **kwargs):
        class Choice:
            def __init__(self, content):
                self.message = type("m", (), {"content": content})
        return type("obj", (), {"choices": [Choice(json.dumps({
            "scenes": [
                {
                    "duration_sec": 10,
                    "visual_description": "v",
                    "voice_lines": [{"role": "n", "text": "hi"}],
                    "broll_hints": [],
                    "tempo": "fast",
                    "transitions": "cut"
                }
            ],
            "total_duration_sec": 10,
            "target": "shorts"
        }))]})

    monkeypatch.setattr(llm_storyboard.client.chat.completions, "create", fake_create)
    board = llm_storyboard.plan_timeline(scenario, "shorts")
    assert board.total_duration_sec == 10
    assert board.scenes[0].tempo == "fast"
