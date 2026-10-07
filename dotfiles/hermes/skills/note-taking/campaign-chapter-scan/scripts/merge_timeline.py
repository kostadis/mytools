#!/usr/bin/env python3
"""Merge per-chapter events.json into a single dated TIMELINE.md with day-change markers.

Usage: merge_timeline.py <parts_dir> <output_md>
  parts_dir : directory containing chNN/events.json subfiles
  output_md : path to write the consolidated timeline

Each events.json is a JSON array of:
  {"chapter": int, "date_label": "DD-MM-Taraskh 1495"|null,
   "sort_date": "1495-MM-DD"|null, "event": "..."}

Sort_date is RECOMPUTED from date_label because agents misread the
DAY-MONTH-Taraskh format (middle number is the month). Undated events
(date_label null) sort last, ordered by chapter number.
"""
import os, re, json, sys

def chnum(d):
    m = re.fullmatch(r'ch(\d+)', d)
    return int(m.group(1)) if m else 10**9

def recompute(label):
    if not label:
        return None
    m = re.search(r'(\d{1,2})-(\d{1,2})-', label)
    if not m:
        return None
    day, mon = m.groups()
    return f"1495-{mon.zfill(2)}-{day.zfill(2)}"

def main():
    parts_dir, out_md = sys.argv[1], sys.argv[2]
    events = []
    for d in sorted(os.listdir(parts_dir)):
        fp = os.path.join(parts_dir, d, 'events.json')
        if not os.path.isfile(fp):
            continue
        for e in json.load(open(fp)):
            sd = recompute(e.get('date_label'))
            events.append({
                'sort': sd or '9999-99-99',
                'chapter': e.get('chapter', chnum(d)),
                'label': e.get('date_label'),
                'event': e.get('event', ''),
            })
    events.sort(key=lambda x: (x['sort'], x['chapter']))

    lines = ["# Campaign Timeline", ""]
    last = None
    for ev in events:
        if ev['label'] and ev['label'] != last:
            lines.append(f"\n--- DAY CHANGE: {ev['label']} ---")
            last = ev['label']
        ch = f"[Ch{ev['chapter']}] " if ev['chapter'] else ""
        lab = f" ({ev['label']})" if ev['label'] else " (undated)"
        lines.append(f"- {ch}{ev['event']}{lab}")
    open(out_md, 'w').write('\n'.join(lines) + '\n')
    print(f"wrote {len(events)} events to {out_md}")

if __name__ == '__main__':
    main()
