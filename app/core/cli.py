import argparse
import json
from app.services import search_trending, transcribe, detect_shots, make_ru_scenario, plan_timeline
from app.integrations import cobalt
from app.schemas import Scenario


def cmd_search(args):
    res = search_trending(args.topic, args.n, args.region, args.after, args.shorts)
    print(json.dumps([c.model_dump() for c in res], ensure_ascii=False, indent=2))


def cmd_analyze(args):
    with cobalt.pull_transient(args.video_id) as (audio_path, video_path):
        transcript = transcribe(audio_path)
        if video_path:
            shots, key_objects = detect_shots(video_path)
        else:
            shots, key_objects = [], []
    print(
        json.dumps(
            {
                "transcript": transcript.model_dump(),
                "shots": [s.model_dump() for s in shots],
                "key_objects": [ko.model_dump() for ko in key_objects],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_scenario(args):
    with cobalt.pull_transient(args.video_id) as (audio_path, video_path):
        transcript = transcribe(audio_path)
        shots, key_objects = detect_shots(video_path) if video_path else ([], [])
    scn = make_ru_scenario(transcript, shots, args.topic, key_objects)
    print(scn.model_dump_json(indent=2, ensure_ascii=False))


def cmd_storyboard(args):
    with open(args.scenario, 'r', encoding='utf-8') as f:
        scn_data = json.load(f)
    scn = Scenario.model_validate(scn_data)
    board = plan_timeline(scn, args.target)
    print(board.model_dump_json(indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command')

    p_search = sub.add_parser('search')
    p_search.add_argument('--topic', required=True)
    p_search.add_argument('--n', type=int, default=5)
    p_search.add_argument('--region', required=True)
    p_search.add_argument('--after', required=True)
    p_search.add_argument(
        '--shorts',
        action='store_true',
        default=True,
        help='Включать YouTube Shorts (по умолчанию)'
    )
    p_search.add_argument(
        '--no-shorts',
        dest='shorts',
        action='store_false',
        help='Исключить YouTube Shorts из результатов'
    )
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
