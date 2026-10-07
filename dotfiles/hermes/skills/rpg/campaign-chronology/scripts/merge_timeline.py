#!/usr/bin/env python3
"""Reusable merge step for a campaign timeline.
Reads per-chapter shards parts/chNN/events.json (each a JSON array of
{"chapter":int,"date_label":str|null,"sort_date":str|null,"event":str}),
recomputes sort_date from date_label, sorts, and writes:
  - timeline.md  : chronological, with ## DAY CHANGE markers
  - timeline.json: flat structured array
  - timeline_dated.md/json : as above but undated events get an inferred
    date from a chapter->date map (optional chapter_dates.json).
Usage:
  python merge_timeline.py <parts_dir> <out_dir> [--dates chapter_dates.json]
"""
import os, re, json, argparse, glob

def parse(dl):
    if not dl:
        return None
    m = re.search(r'(\d{1,2})-(\d{1,2})\s*-?\s*([A-Za-z]+)\s*(\d{4})', dl)
    if not m:
        return None
    return (int(m.group(4)), int(m.group(2)), int(m.group(1)))  # yr,month,day

def sortkey(dl):
    p = parse(dl)
    return p if p else (9999, 99, 999)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('parts_dir')
    ap.add_argument('out_dir')
    ap.add_argument('--dates', default=None, help='optional chapter_dates.json -> {ch:["range",start]}')
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    events = []
    for p in sorted(glob.glob(os.path.join(a.parts_dir, 'ch*', 'events.json'))):
        for e in json.load(open(p)):
            e = dict(e)
            ch = int(re.search(r'ch(\d+)', p).group(1))
            e['_chapter'] = ch
            e['_sort'] = sortkey(e.get('date_label')) if e.get('date_label') else (9999, 99, ch)
            events.append(e)

    cdate = {}
    if a.dates:
        cdate = {int(k): v for k, v in json.load(open(a.dates)).items()}

    for e in events:
        if not e.get('date_label') and e['_chapter'] in cdate:
            e['date_resolved'] = cdate[e['_chapter']][0]
        else:
            e['date_resolved'] = e.get('date_label') or 'undated'

    events.sort(key=lambda e: e['_sort'])

    # timeline.md (day-change markers on date advance)
    lines = ["# Campaign Timeline — Crucial Events\n"]
    cur = None
    for e in events:
        if e['date_resolved'] != cur:
            cur = e['date_resolved']
            head = cur if cur != 'undated' else f"[undated] — from Chapter {e['_chapter']} onward"
            lines.append(f"\n## DAY CHANGE — {head}\n")
        lines.append(f"- [Ch{e['_chapter']}] {e['event']}")
    open(os.path.join(a.out_dir, 'timeline.md'), 'w').write("\n".join(lines) + "\n")

    clean = [{"chapter": e['_chapter'], "date_label": e.get('date_label'),
              "date_resolved": e['date_resolved'], "event": e['event']} for e in events]
    json.dump(clean, open(os.path.join(a.out_dir, 'timeline.json'), 'w'), indent=2)
    print(f"Merged {len(events)} events -> {a.out_dir}/timeline.md + .json")

if __name__ == '__main__':
    main()
