import argparse
import json
from . import youtube_client, media_probe, stt, vision_shots, llm_scenario, llm_storyboard
from .schemas import Scenario, AnalysisResult, VisionInsights


def cmd_search(args):
    res = youtube_client.search_trending(args.topic, args.n, args.region, args.after, args.shorts)
    print(json.dumps([c.model_dump() for c in res], ensure_ascii=False, indent=2))


def cmd_analyze(args):
    with media_probe.pull_transient(args.video_id) as (audio_path, video_path):
        transcript = stt.transcribe(audio_path)
        if video_path:
            vision_data = vision_shots.detect_shots(video_path)
        else:
            vision_data = VisionInsights(shots=[], key_objects=[])
    analysis = AnalysisResult(
        transcript=transcript,
        shots=vision_data.shots,
        key_objects=vision_data.key_objects,
    )
    print(analysis.model_dump_json(indent=2, ensure_ascii=False))


def cmd_scenario(args):
    with media_probe.pull_transient(args.video_id) as (audio_path, video_path):
        transcript = stt.transcribe(audio_path)
        if video_path:
            vision_data = vision_shots.detect_shots(video_path)
        else:
            vision_data = VisionInsights(shots=[], key_objects=[])
    scn = llm_scenario.make_ru_scenario(transcript, vision_data.shots, vision_data.key_objects, args.topic)
    print(scn.model_dump_json(indent=2, ensure_ascii=False))


def cmd_storyboard(args):
    with open(args.scenario, 'r', encoding='utf-8') as f:
        scn_data = json.load(f)
    scn = Scenario.model_validate(scn_data)
    board = llm_storyboard.plan_timeline(scn, args.target)
    print(board.model_dump_json(indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command')

    p_search = sub.add_parser('search')
    p_search.add_argument('--topic', required=True)
    p_search.add_argument('--n', type=int, default=5)
    p_search.add_argument('--region', required=True)
    p_search.add_argument('--after', required=True)
    shorts_group = p_search.add_mutually_exclusive_group()
    shorts_group.add_argument('--shorts', dest='shorts', action='store_true')
    shorts_group.add_argument('--no-shorts', dest='shorts', action='store_false')
    p_search.set_defaults(shorts=True)
    p_search.set_defaults(func=cmd_search)

    p_an = sub.add_parser('analyze')
    p_an.add_argument('--video-id', required=True)
    p_an.set_defaults(func=cmd_analyze)

    p_scn = sub.add_parser('scenario')
    p_scn.add_argument('--video-id', required=True)
    p_scn.add_argument('--topic', required=True)
    p_scn.set_defaults(func=cmd_scenario)

    p_sb = sub.add_parser('storyboard')
    p_sb.add_argument('--scenario', required=True)
    p_sb.add_argument('--target', choices=['shorts', 'youtube'], required=True)
    p_sb.set_defaults(func=cmd_storyboard)

    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    args.func(args)


if __name__ == '__main__':
    main()
