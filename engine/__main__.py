import argparse, json, sys, traceback
from pathlib import Path

from .common import slugify, step


def main():
    p = argparse.ArgumentParser(prog='soundtrack')
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('learn', help='measure the music in a reference video')
    a.add_argument('video'); a.add_argument('--slug'); a.add_argument('--title')
    a = sub.add_parser('speech', help='read what is said in a video or a TG Studio concept folder')
    a.add_argument('source'); a.add_argument('--slug'); a.add_argument('--title')
    a = sub.add_parser('make', help='compose a track for a video')
    a.add_argument('slug'); a.add_argument('theme', nargs='?', default='all'); a.add_argument('--song'); a.add_argument('--under', type=float)
    a.add_argument('--fresh', action='store_true', help='move the last run to runs/<time>/ first')
    a.add_argument('--first', help='genre id to write before the others')
    a = sub.add_parser('export', help='write the video with one track mixed in')
    a.add_argument('slug'); a.add_argument('theme'); a.add_argument('--under', type=float); a.add_argument('--out')
    a = sub.add_parser('mix', help='one genre per part: soundtrack mix <slug> pulse,keys,keys,...')
    a.add_argument('slug'); a.add_argument('ids')
    a = sub.add_parser('viz', help='write the visualizer file for a reference video')
    a.add_argument('slug')
    a = sub.add_parser('levels', help='write the loudness curves the page draws (voice, music)')
    a.add_argument('slug')
    a = sub.add_parser('themes', help='list the genres')
    sub.add_parser('doctor', help='check every program, package and file the engine needs')
    a = sub.add_parser('results', help='every genre made for a video: tests passed, tempo, cue timing')
    a.add_argument('slug')
    a = sub.add_parser('step', help='set a row in the build list on the page')
    a.add_argument('name'); a.add_argument('state', choices=['run', 'ok', 'fail']); a.add_argument('note', nargs='?', default='')
    args = p.parse_args()

    if args.cmd == 'results':
        from .common import WORK, read_json
        rows = [read_json(f) for f in sorted((WORK / args.slug / 'tries').glob('*/try.json'))]
        if not rows: sys.exit(f'nothing made for {args.slug} yet: soundtrack make {args.slug} all')
        for t in sorted(rows, key=lambda t: (not t.get('passed'), t.get('score', {}).get('cueErrorMs', 999))):
            g = t.get('gates') or []
            print(f"{t['id']:<10} {t['name']:<20} {'pass' if t.get('passed') else 'FAIL'} {sum(x['ok'] for x in g)}/{len(g)}  {t.get('bpm', '')} BPM  {t.get('key', '')}  cue {t.get('score', {}).get('cueErrorMs', '?')} ms")
        return
    if args.cmd == 'doctor':
        from .doctor import doctor
        sys.exit(doctor())
    if args.cmd == 'mix':
        from .stitch import stitch
        return stitch(args.slug, args.ids.split(','))
    if args.cmd == 'viz':
        from .common import WORK, read_json
        from .viz import write_track
        import soundfile as sf
        d, ref = WORK / args.slug, read_json(WORK.parent / 'research' / args.slug / 'ref.json')
        x, sr = sf.read(d / 'music.wav', always_2d=True)
        cuts = sorted([0.0, ref['seconds']] + [v for b in ref['breaks'] for v in (b['t'], b['t'] + b['d'])])
        parts = [{'t0': a, 't1': z, 'kind': 'break' if any(abs(a - b['t']) < 0.01 for b in ref['breaks']) else 'play', 'level': 3} for a, z in zip(cuts[:-1], cuts[1:])]
        write_track(d / 'track.json', x.T, sr, args.slug, parts, ref['bpm'])
        return print('track.json written for', args.slug)
    if args.cmd == 'levels':
        from .common import WORK, read_json, write_json
        from .mix import dbfs, write_levels
        import numpy as np, soundfile as sf
        d = WORK / args.slug
        write_levels(args.slug, d / 'music.wav' if (d / 'music.wav').exists() else None)
        for t in (d / 'tries').glob('*/try.json') if (d / 'tries').exists() else []:
            x, _ = sf.read(t.parent / 'bed.wav', always_2d=True)
            row = read_json(t); row['levelMedian'] = round(float(np.median(dbfs(x.T))), 1); write_json(t, row)
        return print('levels written for', args.slug)
    if args.cmd == 'step':
        return step(args.name, args.state, args.note)
    if args.cmd == 'learn':
        from .reference import measure
        slug = args.slug or slugify(Path(args.video).stem)
        step(f'Measure reference: {args.title or slug}', 'run')
        r = measure(args.video, slug, args.title)
        step(f'Measure reference: {args.title or slug}', 'ok', f"{r['bpm']} BPM, {r['key']}, music {r['under']} LU under the voice, {len(r['breaks'])} full stops")
        print(json.dumps({k: r[k] for k in ('slug', 'bpm', 'key', 'under', 'share', 'breaks')}, indent=1))
    elif args.cmd == 'speech':
        from .speech import from_concept, from_video
        src = Path(args.source)
        s = from_concept(src) if src.is_dir() else from_video(src, args.slug or slugify(src.stem), args.title)
        print(json.dumps({'slug': s['slug'], 'seconds': s['seconds'], 'words': len(s['words']), 'sentences': len(s['sentences']), 'pauses': len(s['pauses']), 'sections': s['sections'], 'pivots': [x['text'] for x in s['sentences'] if x.get('pivot')]}, indent=1))
    elif args.cmd == 'make':
        from .make import make
        make(args.slug, args.theme, song=args.song, under=args.under, fresh=args.fresh, first=args.first)
    elif args.cmd == 'export':
        from .mix import export
        print(json.dumps(export(args.slug, args.theme, under=args.under, out=args.out), indent=1))
    elif args.cmd == 'themes':
        from .compose import themes
        for t in themes().values():
            print(f"{t['id']:10} {t['name']:18} {t['bpm'][0]}-{t['bpm'][1]} BPM  {t['key']} {t['mode']}  {t['about']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        traceback.print_exc()
        sys.exit(f'FAILED: {err}')
